"""Database models for SWE-bench A2A"""

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, JSON, Text,
    ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class Agent(Base):
    """Agent registration and metadata"""
    __tablename__ = "agents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    agent_type = Column(String(50), nullable=False)  # green, purple, red
    capabilities = Column(JSON)
    endpoints = Column(JSON)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tasks = relationship("Task", back_populates="agent")
    assessments = relationship("Assessment", back_populates="agent")
    results = relationship("Result", back_populates="agent")
    
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_agent_name_version"),
        Index("idx_agent_type", "agent_type"),
        Index("idx_agent_created", "created_at"),
    )


class Task(Base):
    """Task tracking and lifecycle"""
    __tablename__ = "tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String(36), ForeignKey("agents.id"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False)  # created, in_progress, completed, failed
    scenario_id = Column(String(255))
    resources = Column(JSON)
    constraints = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Relationships
    agent = relationship("Agent", back_populates="tasks")
    assessment = relationship("Assessment", back_populates="task", uselist=False)
    trajectories = relationship("Trajectory", back_populates="task", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_task_status", "status"),
        Index("idx_task_agent", "agent_id"),
        Index("idx_task_scenario", "scenario_id"),
        Index("idx_task_created", "created_at"),
    )


class Assessment(Base):
    """Assessment results and metrics"""
    __tablename__ = "assessments"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id"), unique=True)
    agent_id = Column(String(36), ForeignKey("agents.id"))
    scenario_id = Column(String(255), nullable=False)
    
    # Evaluation results
    passed = Column(Boolean, default=False)
    tests_passed = Column(Integer, default=0)
    tests_failed = Column(Integer, default=0)
    patch_applied = Column(Boolean, default=False)
    
    # Performance metrics
    execution_time = Column(Float)  # seconds
    token_usage = Column(Integer)
    memory_usage = Column(Float)  # MB
    api_calls = Column(Integer)
    
    # Quality metrics
    patch_size = Column(Integer)  # lines changed
    confidence_score = Column(Float)
    ambiguity_level = Column(String(50))
    mutation_applied = Column(Boolean, default=False)
    
    # Artifacts
    patch_content = Column(Text)
    error_log = Column(Text)
    meta_data = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", back_populates="assessment")
    agent = relationship("Agent", back_populates="assessments")
    result = relationship("Result", back_populates="assessment", uselist=False)
    
    __table_args__ = (
        Index("idx_assessment_passed", "passed"),
        Index("idx_assessment_scenario", "scenario_id"),
        Index("idx_assessment_created", "created_at"),
        CheckConstraint("tests_passed >= 0", name="ck_tests_passed_positive"),
        CheckConstraint("tests_failed >= 0", name="ck_tests_failed_positive"),
    )


class Trajectory(Base):
    """Execution trajectory and action logging"""
    __tablename__ = "trajectories"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    
    # Action details
    action_type = Column(String(100), nullable=False)  # search, read, write, execute, think
    action_target = Column(String(500))  # file path, command, etc.
    action_input = Column(Text)
    action_output = Column(Text)
    
    # Performance
    duration_ms = Column(Integer)
    tokens_used = Column(Integer)
    
    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    meta_data = Column(JSON)
    
    # Relationships
    task = relationship("Task", back_populates="trajectories")
    
    __table_args__ = (
        Index("idx_trajectory_task", "task_id"),
        Index("idx_trajectory_sequence", "task_id", "sequence_number"),
        Index("idx_trajectory_action", "action_type"),
        Index("idx_trajectory_timestamp", "timestamp"),
        UniqueConstraint("task_id", "sequence_number", name="uq_task_sequence"),
    )


class Result(Base):
    """Final results for leaderboard"""
    __tablename__ = "results"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id"), unique=True)
    agent_id = Column(String(36), ForeignKey("agents.id"))
    scenario_id = Column(String(255), nullable=False)
    
    # Scores
    success_rate = Column(Float)  # 0-1
    efficiency_score = Column(Float)  # 0-100
    quality_score = Column(Float)  # 0-100
    overall_score = Column(Float)  # 0-100
    
    # Rankings
    rank_overall = Column(Integer)
    rank_scenario = Column(Integer)
    rank_daily = Column(Integer)
    
    # Statistics
    total_actions = Column(Integer)
    unique_files_accessed = Column(Integer)
    exploration_breadth = Column(Float)  # measure of codebase coverage
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    assessment = relationship("Assessment", back_populates="result")
    agent = relationship("Agent", back_populates="results")
    leaderboard_entries = relationship("Leaderboard", back_populates="result")
    
    __table_args__ = (
        Index("idx_result_agent", "agent_id"),
        Index("idx_result_scenario", "scenario_id"),
        Index("idx_result_overall_score", "overall_score"),
        Index("idx_result_created", "created_at"),
    )


class Leaderboard(Base):
    """Leaderboard entries and historical tracking"""
    __tablename__ = "leaderboard"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    result_id = Column(String(36), ForeignKey("results.id"))
    agent_name = Column(String(255), nullable=False)
    agent_version = Column(String(50), nullable=False)
    
    # Leaderboard type
    board_type = Column(String(50), nullable=False)  # overall, daily, weekly, scenario
    board_date = Column(DateTime, nullable=False)
    
    # Position
    rank = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)
    
    # Metrics snapshot
    metrics = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    result = relationship("Result", back_populates="leaderboard_entries")
    
    __table_args__ = (
        Index("idx_leaderboard_type", "board_type"),
        Index("idx_leaderboard_date", "board_date"),
        Index("idx_leaderboard_rank", "board_type", "board_date", "rank"),
        UniqueConstraint("result_id", "board_type", "board_date", name="uq_leaderboard_entry"),
    )


class Scenario(Base):
    """Scenario metadata and statistics"""
    __tablename__ = "scenarios"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id = Column(String(255), unique=True, nullable=False)
    repo = Column(String(255), nullable=False)
    base_commit = Column(String(50))
    
    # Scenario details
    problem_statement = Column(Text)
    difficulty = Column(String(50))  # easy, medium, hard
    category = Column(String(100))  # bug_fix, feature, refactor
    
    # Freshness tracking
    is_fresh = Column(Boolean, default=False)
    source = Column(String(50))  # original, harvested, synthetic
    harvested_at = Column(DateTime)
    github_issue_url = Column(String(500))
    
    # Statistics
    attempt_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    average_score = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_scenario_instance", "instance_id"),
        Index("idx_scenario_repo", "repo"),
        Index("idx_scenario_fresh", "is_fresh"),
        Index("idx_scenario_difficulty", "difficulty"),
    )


class Team(Base):
    """Multi-agent team registration"""
    __tablename__ = "teams"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), unique=True, nullable=False)
    
    # Team composition
    architect_agent_id = Column(String(36), ForeignKey("agents.id"))
    developer_agent_id = Column(String(36), ForeignKey("agents.id"))
    reviewer_agent_id = Column(String(36), ForeignKey("agents.id"))
    
    # Metadata
    description = Column(Text)
    configuration = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_team_name", "name"),
        Index("idx_team_created", "created_at"),
    )