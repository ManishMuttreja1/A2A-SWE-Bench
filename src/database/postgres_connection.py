"""PostgreSQL Database Connection with Async Support"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncpg
import json

logger = logging.getLogger(__name__)


class PostgresConnection:
    """
    Async PostgreSQL connection manager for SWE-bench.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://swebench:swebench_secure_pass_2024@localhost:5432/swebench"
        )
        self.pool: Optional[asyncpg.Pool] = None
        
    async def initialize(self):
        """Initialize connection pool and create tables"""
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            
            # Create tables
            await self._create_tables()
            
            logger.info("PostgreSQL connection pool initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            raise
    
    async def _create_tables(self):
        """Create database tables if they don't exist"""
        async with self.pool.acquire() as conn:
            # Tasks table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id UUID PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    metadata JSONB,
                    resources JSONB,
                    constraints JSONB,
                    artifacts JSONB,
                    metrics JSONB
                )
            """)
            
            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status 
                ON tasks(status)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created 
                ON tasks(created_at DESC)
            """)
            
            # Evaluations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    id UUID PRIMARY KEY,
                    task_id UUID REFERENCES tasks(id),
                    instance_id VARCHAR(255),
                    repo VARCHAR(255),
                    commit_hash VARCHAR(255),
                    patch TEXT,
                    test_results JSONB,
                    verification_status VARCHAR(50),
                    passed BOOLEAN DEFAULT FALSE,
                    execution_time FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB
                )
            """)
            
            # Create indexes for evaluations
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluations_task 
                ON evaluations(task_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluations_instance 
                ON evaluations(instance_id)
            """)
            
            # Metrics table for tracking performance
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metric_type VARCHAR(100),
                    metric_name VARCHAR(255),
                    value FLOAT,
                    labels JSONB,
                    metadata JSONB
                )
            """)
            
            # Create index for metrics queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_type_time 
                ON metrics(metric_type, timestamp DESC)
            """)
            
            logger.info("Database tables created successfully")
    
    async def create_task(self, task_data: Dict[str, Any]) -> str:
        """Create a new task"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO tasks (
                    id, title, description, status, 
                    metadata, resources, constraints
                ) VALUES (
                    gen_random_uuid(), $1, $2, $3, $4, $5, $6
                ) RETURNING id
            """,
                task_data.get("title", ""),
                task_data.get("description", ""),
                "pending",
                json.dumps(task_data.get("metadata", {})),
                json.dumps(task_data.get("resources", {})),
                json.dumps(task_data.get("constraints", {}))
            )
            
            return str(result["id"])
    
    async def update_task(self, task_id: str, updates: Dict[str, Any]):
        """Update task status and data"""
        async with self.pool.acquire() as conn:
            # Build dynamic update query
            set_clauses = []
            values = []
            param_count = 1
            
            for key, value in updates.items():
                if key in ["status", "title", "description"]:
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(value)
                elif key in ["metadata", "resources", "constraints", "artifacts", "metrics"]:
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(json.dumps(value))
                elif key == "completed_at":
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(value)
                param_count += 1
            
            # Always update updated_at
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            
            if set_clauses:
                query = f"""
                    UPDATE tasks 
                    SET {', '.join(set_clauses)}
                    WHERE id = ${param_count}
                """
                values.append(task_id)
                
                await conn.execute(query, *values)
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM tasks WHERE id = $1
            """, task_id)
            
            if row:
                return dict(row)
            return None
    
    async def get_pending_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending tasks"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM tasks 
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]
    
    async def create_evaluation(self, eval_data: Dict[str, Any]) -> str:
        """Create evaluation record"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO evaluations (
                    id, task_id, instance_id, repo, commit_hash,
                    patch, test_results, verification_status,
                    passed, execution_time, metadata
                ) VALUES (
                    gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
                ) RETURNING id
            """,
                eval_data.get("task_id"),
                eval_data.get("instance_id"),
                eval_data.get("repo"),
                eval_data.get("commit_hash"),
                eval_data.get("patch"),
                json.dumps(eval_data.get("test_results", {})),
                eval_data.get("verification_status", "pending"),
                eval_data.get("passed", False),
                eval_data.get("execution_time", 0.0),
                json.dumps(eval_data.get("metadata", {}))
            )
            
            return str(result["id"])
    
    async def get_evaluation_stats(self) -> Dict[str, Any]:
        """Get evaluation statistics"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed,
                    SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) as failed,
                    AVG(execution_time) as avg_time,
                    MIN(execution_time) as min_time,
                    MAX(execution_time) as max_time
                FROM evaluations
            """)
            
            return dict(stats)
    
    async def record_metric(
        self,
        metric_type: str,
        metric_name: str,
        value: float,
        labels: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ):
        """Record a metric"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO metrics (
                    metric_type, metric_name, value, labels, metadata
                ) VALUES ($1, $2, $3, $4, $5)
            """,
                metric_type,
                metric_name,
                value,
                json.dumps(labels or {}),
                json.dumps(metadata or {})
            )
    
    async def get_metrics(
        self,
        metric_type: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get metrics by type and time range"""
        async with self.pool.acquire() as conn:
            query = "SELECT * FROM metrics WHERE metric_type = $1"
            params = [metric_type]
            param_count = 2
            
            if start_time:
                query += f" AND timestamp >= ${param_count}"
                params.append(start_time)
                param_count += 1
            
            if end_time:
                query += f" AND timestamp <= ${param_count}"
                params.append(end_time)
            
            query += " ORDER BY timestamp DESC"
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    async def cleanup(self):
        """Clean up connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")