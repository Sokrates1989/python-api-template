from neo4j import GraphDatabase
from api.settings import settings


class Neo4jHandler:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URL,
            auth=(settings.DB_USER, settings.DB_PASSWORD)
        )

    def close(self):
        if self.driver:
            self.driver.close()

    def test_query(self):
        with self.driver.session() as session:
            result = session.run("MATCH (n) RETURN n LIMIT 1")
            return [record["n"] for record in result]
