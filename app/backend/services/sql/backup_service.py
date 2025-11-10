"""Database backup and restore service for SQL databases."""
import subprocess
import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
import gzip
import shutil
from api.settings import settings


class BackupService:
    """Service for creating and restoring database backups."""
    
    def __init__(self):
        """Initialize backup service."""
        self.backup_dir = Path("/app/backups")
        self.backup_dir.mkdir(exist_ok=True)
        
    def create_backup(self, compress: bool = True) -> tuple[str, Path]:
        """
        Create a database backup.
        
        Args:
            compress: Whether to compress the backup with gzip
            
        Returns:
            Tuple of (filename, filepath)
            
        Raises:
            Exception: If backup creation fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_type = settings.DB_TYPE.lower()
        
        if db_type in ["postgresql", "postgres"]:
            return self._backup_postgresql(timestamp, compress)
        elif db_type == "mysql":
            return self._backup_mysql(timestamp, compress)
        elif db_type == "sqlite":
            return self._backup_sqlite(timestamp, compress)
        else:
            raise ValueError(f"Backup not supported for database type: {db_type}")
    
    def _backup_postgresql(self, timestamp: str, compress: bool) -> tuple[str, Path]:
        """Create PostgreSQL backup using pg_dump."""
        filename = f"backup_postgresql_{timestamp}.sql"
        if compress:
            filename += ".gz"
        
        filepath = self.backup_dir / filename
        
        # Build pg_dump command
        env = os.environ.copy()
        env['PGPASSWORD'] = settings.DB_PASSWORD
        
        cmd = [
            'pg_dump',
            '-h', settings.DB_HOST,
            '-p', str(settings.DB_PORT),
            '-U', settings.DB_USER,
            '-d', settings.DB_NAME,
            '--no-owner',  # Don't include ownership commands
            '--no-acl',    # Don't include access privileges
            '-F', 'p',     # Plain text format
        ]
        
        try:
            # Run pg_dump
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                check=True,
                text=True
            )
            
            # Write output
            if compress:
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    f.write(result.stdout)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
            
            return filename, filepath
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"PostgreSQL backup failed: {e.stderr}")
    
    def _backup_mysql(self, timestamp: str, compress: bool) -> tuple[str, Path]:
        """Create MySQL backup using mysqldump."""
        filename = f"backup_mysql_{timestamp}.sql"
        if compress:
            filename += ".gz"
        
        filepath = self.backup_dir / filename
        
        cmd = [
            'mysqldump',
            '-h', settings.DB_HOST,
            '-P', str(settings.DB_PORT),
            '-u', settings.DB_USER,
            f'-p{settings.DB_PASSWORD}',
            settings.DB_NAME,
            '--single-transaction',  # Consistent backup
            '--skip-lock-tables',    # Don't lock tables
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True
            )
            
            if compress:
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    f.write(result.stdout)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
            
            return filename, filepath
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"MySQL backup failed: {e.stderr}")
    
    def _backup_sqlite(self, timestamp: str, compress: bool) -> tuple[str, Path]:
        """Create SQLite backup by copying the database file."""
        filename = f"backup_sqlite_{timestamp}.db"
        if compress:
            filename += ".gz"
        
        filepath = self.backup_dir / filename
        
        # SQLite database is a file, just copy it
        db_file = Path(settings.DB_NAME)
        
        if not db_file.exists():
            raise Exception(f"SQLite database file not found: {db_file}")
        
        try:
            if compress:
                with open(db_file, 'rb') as f_in:
                    with gzip.open(filepath, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(db_file, filepath)
            
            return filename, filepath
            
        except Exception as e:
            raise Exception(f"SQLite backup failed: {str(e)}")
    
    def restore_backup(self, backup_file: Path) -> None:
        """
        Restore database from backup file.
        
        Args:
            backup_file: Path to backup file
            
        Raises:
            Exception: If restore fails
        """
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        db_type = settings.DB_TYPE.lower()
        
        # Check if file is compressed
        is_compressed = backup_file.suffix == '.gz'
        
        if db_type in ["postgresql", "postgres"]:
            self._restore_postgresql(backup_file, is_compressed)
        elif db_type == "mysql":
            self._restore_mysql(backup_file, is_compressed)
        elif db_type == "sqlite":
            self._restore_sqlite(backup_file, is_compressed)
        else:
            raise ValueError(f"Restore not supported for database type: {db_type}")
    
    def _restore_postgresql(self, backup_file: Path, is_compressed: bool) -> None:
        """Restore PostgreSQL database using psql."""
        env = os.environ.copy()
        env['PGPASSWORD'] = settings.DB_PASSWORD
        
        cmd = [
            'psql',
            '-h', settings.DB_HOST,
            '-p', str(settings.DB_PORT),
            '-U', settings.DB_USER,
            '-d', settings.DB_NAME,
        ]
        
        try:
            # Read backup file
            if is_compressed:
                with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                    sql_content = f.read()
            else:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
            
            # Execute SQL
            result = subprocess.run(
                cmd,
                env=env,
                input=sql_content,
                capture_output=True,
                check=True,
                text=True
            )
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"PostgreSQL restore failed: {e.stderr}")
    
    def _restore_mysql(self, backup_file: Path, is_compressed: bool) -> None:
        """Restore MySQL database using mysql."""
        cmd = [
            'mysql',
            '-h', settings.DB_HOST,
            '-P', str(settings.DB_PORT),
            '-u', settings.DB_USER,
            f'-p{settings.DB_PASSWORD}',
            settings.DB_NAME,
        ]
        
        try:
            if is_compressed:
                with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                    sql_content = f.read()
            else:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
            
            result = subprocess.run(
                cmd,
                input=sql_content,
                capture_output=True,
                check=True,
                text=True
            )
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"MySQL restore failed: {e.stderr}")
    
    def _restore_sqlite(self, backup_file: Path, is_compressed: bool) -> None:
        """Restore SQLite database by replacing the database file."""
        db_file = Path(settings.DB_NAME)
        
        # Backup current database before replacing
        if db_file.exists():
            backup_current = db_file.with_suffix('.db.backup')
            shutil.copy2(db_file, backup_current)
        
        try:
            if is_compressed:
                with gzip.open(backup_file, 'rb') as f_in:
                    with open(db_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(backup_file, db_file)
                
        except Exception as e:
            # Restore original if restore failed
            if db_file.exists():
                backup_current = db_file.with_suffix('.db.backup')
                if backup_current.exists():
                    shutil.copy2(backup_current, db_file)
            raise Exception(f"SQLite restore failed: {str(e)}")
    
    def list_backups(self) -> list[dict]:
        """
        List all available backups.
        
        Returns:
            List of backup info dictionaries
        """
        backups = []
        
        for backup_file in self.backup_dir.glob("backup_*"):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "compressed": backup_file.suffix == '.gz'
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
