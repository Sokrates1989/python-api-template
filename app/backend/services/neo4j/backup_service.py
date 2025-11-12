"""Database backup and restore service for Neo4j."""
import subprocess
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
import gzip
import json
from neo4j import GraphDatabase
from api.settings import settings


class Neo4jBackupService:
    """Service for creating and restoring Neo4j database backups."""
    
    def __init__(self):
        """Initialize Neo4j backup service."""
        self.backup_dir = Path("/app/backups")
        self.backup_dir.mkdir(exist_ok=True)
        
    def create_backup(self, compress: bool = True) -> tuple[str, Path]:
        """
        Create a Neo4j database backup using Cypher export.
        
        This exports all nodes and relationships as Cypher CREATE statements.
        
        Args:
            compress: Whether to compress the backup with gzip
            
        Returns:
            Tuple of (filename, filepath)
            
        Raises:
            Exception: If backup creation fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_neo4j_{timestamp}.cypher"
        if compress:
            filename += ".gz"
        
        filepath = self.backup_dir / filename
        
        try:
            # Connect to Neo4j
            driver = GraphDatabase.driver(
                f"bolt://{settings.DB_HOST}:{settings.DB_PORT}",
                auth=(settings.DB_USER, settings.get_db_password())
            )
            
            cypher_statements = []
            
            with driver.session() as session:
                # Export all nodes
                print("📦 Exporting nodes...")
                result = session.run("MATCH (n) RETURN n")
                for record in result:
                    node = record["n"]
                    labels = ":".join(node.labels)
                    props = dict(node.items())
                    
                    # Create Cypher CREATE statement
                    props_str = ", ".join([f"{k}: {self._format_value(v)}" for k, v in props.items()])
                    cypher = f"CREATE (:{labels} {{{props_str}}});"
                    cypher_statements.append(cypher)
                
                # Export all relationships
                print("📦 Exporting relationships...")
                result = session.run("""
                    MATCH (a)-[r]->(b)
                    RETURN 
                        labels(a) as start_labels,
                        properties(a) as start_props,
                        type(r) as rel_type,
                        properties(r) as rel_props,
                        labels(b) as end_labels,
                        properties(b) as end_props
                """)
                
                for record in result:
                    start_labels = ":".join(record["start_labels"])
                    start_props = self._format_props(record["start_props"])
                    rel_type = record["rel_type"]
                    rel_props = self._format_props(record["rel_props"])
                    end_labels = ":".join(record["end_labels"])
                    end_props = self._format_props(record["end_props"])
                    
                    # Create Cypher MATCH + CREATE statement for relationship
                    cypher = (
                        f"MATCH (a:{start_labels} {start_props}), "
                        f"(b:{end_labels} {end_props}) "
                        f"CREATE (a)-[:{rel_type} {rel_props}]->(b);"
                    )
                    cypher_statements.append(cypher)
            
            driver.close()
            
            # Write to file
            content = "\n".join(cypher_statements)
            
            if compress:
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    f.write(content)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            print(f"✅ Exported {len(cypher_statements)} statements")
            return filename, filepath
            
        except Exception as e:
            raise Exception(f"Neo4j backup failed: {str(e)}")
    
    def _format_value(self, value) -> str:
        """Format a value for Cypher."""
        if isinstance(value, str):
            # Escape quotes and backslashes
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        elif isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            formatted_items = [self._format_value(item) for item in value]
            return f"[{', '.join(formatted_items)}]"
        elif value is None:
            return 'null'
        else:
            return f'"{str(value)}"'
    
    def _format_props(self, props: dict) -> str:
        """Format properties dictionary for Cypher."""
        if not props:
            return ""
        
        props_str = ", ".join([f"{k}: {self._format_value(v)}" for k, v in props.items()])
        return f"{{{props_str}}}"
    
    def create_backup_apoc(self, compress: bool = True) -> tuple[str, Path]:
        """
        Create a Neo4j database backup using APOC export (if available).
        
        This requires the APOC plugin to be installed in Neo4j.
        
        Args:
            compress: Whether to compress the backup with gzip
            
        Returns:
            Tuple of (filename, filepath)
            
        Raises:
            Exception: If backup creation fails or APOC not available
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_neo4j_apoc_{timestamp}.cypher"
        if compress:
            filename += ".gz"
        
        filepath = self.backup_dir / filename
        
        try:
            driver = GraphDatabase.driver(
                f"bolt://{settings.DB_HOST}:{settings.DB_PORT}",
                auth=(settings.DB_USER, settings.get_db_password())
            )
            
            with driver.session() as session:
                # Use APOC to export database
                result = session.run("""
                    CALL apoc.export.cypher.all(null, {
                        stream: true,
                        format: 'cypher-shell'
                    })
                    YIELD cypherStatements
                    RETURN cypherStatements
                """)
                
                record = result.single()
                if not record:
                    raise Exception("APOC export returned no data")
                
                content = record["cypherStatements"]
            
            driver.close()
            
            # Write to file
            if compress:
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    f.write(content)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            return filename, filepath
            
        except Exception as e:
            if "apoc" in str(e).lower():
                raise Exception("APOC plugin not available. Use standard backup method instead.")
            raise Exception(f"Neo4j APOC backup failed: {str(e)}")
    
    def restore_backup(self, backup_file: Path) -> None:
        """
        Restore Neo4j database from backup file.
        
        ⚠️ WARNING: This will delete all existing data first!
        
        Args:
            backup_file: Path to backup file
            
        Raises:
            Exception: If restore fails
        """
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        # Check if file is compressed
        is_compressed = backup_file.suffix == '.gz'
        
        try:
            # Read backup file
            if is_compressed:
                with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                    cypher_statements = f.read()
            else:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    cypher_statements = f.read()
            
            # Connect to Neo4j
            driver = GraphDatabase.driver(
                f"bolt://{settings.DB_HOST}:{settings.DB_PORT}",
                auth=(settings.DB_USER, settings.get_db_password())
            )
            
            with driver.session() as session:
                # Clear existing data
                print("🗑️  Clearing existing data...")
                session.run("MATCH (n) DETACH DELETE n")
                
                # Execute each Cypher statement
                print("📥 Restoring data...")
                statements = [s.strip() for s in cypher_statements.split(';') if s.strip()]
                
                for i, statement in enumerate(statements):
                    if statement:
                        try:
                            session.run(statement)
                            if (i + 1) % 100 == 0:
                                print(f"   Executed {i + 1}/{len(statements)} statements...")
                        except Exception as e:
                            print(f"   Warning: Failed to execute statement {i + 1}: {e}")
                            # Continue with other statements
                
                print(f"✅ Executed {len(statements)} statements")
            
            driver.close()
            
        except Exception as e:
            raise Exception(f"Neo4j restore failed: {str(e)}")
    
    def list_backups(self) -> list[dict]:
        """
        List all available Neo4j backups.
        
        Returns:
            List of backup info dictionaries
        """
        backups = []
        
        for backup_file in self.backup_dir.glob("backup_neo4j_*.cypher*"):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "compressed": backup_file.suffix == '.gz',
                "backup_type": "apoc" if "apoc" in backup_file.name else "cypher"
            })
        
        # Sort by creation time, newest first
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return backups
    
    def delete_backup(self, filename: str) -> None:
        """
        Delete a backup file.
        
        Args:
            filename: Name of backup file to delete
            
        Raises:
            FileNotFoundError: If backup file doesn't exist
        """
        filepath = self.backup_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Backup file not found: {filename}")
        
        # Security check: ensure file is in backup directory
        if not filepath.resolve().parent == self.backup_dir.resolve():
            raise ValueError("Invalid backup filename")
        
        filepath.unlink()
    
    def get_backup_path(self, filename: str) -> Path:
        """
        Get full path to backup file.
        
        Args:
            filename: Name of backup file
            
        Returns:
            Path to backup file
            
        Raises:
            FileNotFoundError: If backup file doesn't exist
        """
        filepath = self.backup_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Backup file not found: {filename}")
        
        # Security check
        if not filepath.resolve().parent == self.backup_dir.resolve():
            raise ValueError("Invalid backup filename")
        
        return filepath
    
    def get_database_stats(self) -> dict:
        """
        Get current database statistics.
        
        Returns:
            Dictionary with node and relationship counts
        """
        try:
            driver = GraphDatabase.driver(
                f"bolt://{settings.DB_HOST}:{settings.DB_PORT}",
                auth=(settings.DB_USER, settings.get_db_password())
            )
            
            with driver.session() as session:
                # Count nodes
                node_result = session.run("MATCH (n) RETURN count(n) as count")
                node_count = node_result.single()["count"]
                
                # Count relationships
                rel_result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                rel_count = rel_result.single()["count"]
                
                # Get node labels
                labels_result = session.run("CALL db.labels()")
                labels = [record["label"] for record in labels_result]
                
                # Get relationship types
                types_result = session.run("CALL db.relationshipTypes()")
                rel_types = [record["relationshipType"] for record in types_result]
            
            driver.close()
            
            return {
                "node_count": node_count,
                "relationship_count": rel_count,
                "labels": labels,
                "relationship_types": rel_types
            }
            
        except Exception as e:
            raise Exception(f"Failed to get database stats: {str(e)}")
