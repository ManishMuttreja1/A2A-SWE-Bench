"""Leaderboard service for tracking agent performance"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from ..database import get_session, Result, Agent, Leaderboard, Assessment, Scenario
from ..trajectory import TrajectoryAnalyzer
from .scoring import ScoringAlgorithm

logger = logging.getLogger(__name__)


class LeaderboardService:
    """
    Manages leaderboards and rankings for SWE-bench agents.
    """
    
    def __init__(self):
        self.scoring = ScoringAlgorithm()
        self.analyzer = TrajectoryAnalyzer()
        
        # Cache for performance
        self.cache = {
            "overall": None,
            "daily": None,
            "weekly": None,
            "by_scenario": {},
            "last_update": None
        }
        
        self.cache_ttl = 300  # 5 minutes
    
    async def update_leaderboard(
        self,
        assessment_id: str
    ) -> Dict[str, Any]:
        """
        Update leaderboard after a new assessment.
        
        Args:
            assessment_id: Assessment ID to process
            
        Returns:
            Update result
        """
        with get_session() as session:
            # Get assessment
            assessment = session.query(Assessment).filter_by(id=assessment_id).first()
            
            if not assessment:
                logger.error(f"Assessment {assessment_id} not found")
                return {"error": "Assessment not found"}
            
            # Analyze trajectory
            trajectory_analysis = await self.analyzer.analyze_trajectory(assessment.task_id)
            
            # Calculate scores
            scores = self.scoring.calculate_scores(assessment, trajectory_analysis)
            
            # Create or update result
            result = session.query(Result).filter_by(assessment_id=assessment_id).first()
            
            if not result:
                result = Result(
                    assessment_id=assessment_id,
                    agent_id=assessment.agent_id,
                    scenario_id=assessment.scenario_id
                )
                session.add(result)
            
            # Update scores
            result.success_rate = scores["success_rate"]
            result.efficiency_score = scores["efficiency_score"]
            result.quality_score = scores["quality_score"]
            result.overall_score = scores["overall_score"]
            
            # Update statistics
            result.total_actions = trajectory_analysis["metrics"]["total_actions"]
            result.unique_files_accessed = trajectory_analysis["file_analysis"]["total_files_accessed"]
            result.exploration_breadth = trajectory_analysis["patterns"]["exploration_breadth"]
            
            session.commit()
            
            # Update rankings
            await self._update_rankings(session, result)
            
            # Invalidate cache
            self.cache["last_update"] = None
            
            logger.info(f"Updated leaderboard for assessment {assessment_id}")
            
            return {
                "success": True,
                "result_id": result.id,
                "overall_score": result.overall_score,
                "rank": result.rank_overall
            }
    
    async def _update_rankings(
        self,
        session,
        result: Result
    ):
        """Update rankings for all leaderboards"""
        # Update overall ranking
        overall_rank = await self._calculate_rank(
            session,
            result.agent_id,
            "overall"
        )
        result.rank_overall = overall_rank
        
        # Update scenario-specific ranking
        scenario_rank = await self._calculate_rank(
            session,
            result.agent_id,
            "scenario",
            scenario_id=result.scenario_id
        )
        result.rank_scenario = scenario_rank
        
        # Update daily ranking
        daily_rank = await self._calculate_rank(
            session,
            result.agent_id,
            "daily"
        )
        result.rank_daily = daily_rank
        
        # Create leaderboard entries
        await self._create_leaderboard_entries(session, result)
        
        session.commit()
    
    async def _calculate_rank(
        self,
        session,
        agent_id: str,
        board_type: str,
        scenario_id: Optional[str] = None
    ) -> int:
        """Calculate rank for an agent"""
        query = session.query(Result)
        
        if board_type == "scenario" and scenario_id:
            query = query.filter_by(scenario_id=scenario_id)
        elif board_type == "daily":
            today = datetime.utcnow().date()
            query = query.filter(
                Result.created_at >= datetime.combine(today, datetime.min.time())
            )
        
        # Get all results ordered by score
        results = query.order_by(Result.overall_score.desc()).all()
        
        # Find rank
        for i, r in enumerate(results, 1):
            if r.agent_id == agent_id:
                return i
        
        return len(results) + 1
    
    async def _create_leaderboard_entries(
        self,
        session,
        result: Result
    ):
        """Create leaderboard entries for different boards"""
        agent = session.query(Agent).filter_by(id=result.agent_id).first()
        
        if not agent:
            return
        
        # Create entries for different board types
        board_types = ["overall", "daily", "weekly", f"scenario_{result.scenario_id}"]
        
        for board_type in board_types:
            # Check if entry exists
            existing = session.query(Leaderboard).filter_by(
                result_id=result.id,
                board_type=board_type,
                board_date=datetime.utcnow().date()
            ).first()
            
            if not existing:
                entry = Leaderboard(
                    result_id=result.id,
                    agent_name=agent.name,
                    agent_version=agent.version,
                    board_type=board_type,
                    board_date=datetime.utcnow().date(),
                    rank=getattr(result, f"rank_{board_type.split('_')[0]}", 999),
                    score=result.overall_score,
                    metrics={
                        "success_rate": result.success_rate,
                        "efficiency_score": result.efficiency_score,
                        "quality_score": result.quality_score
                    }
                )
                session.add(entry)
    
    async def get_leaderboard(
        self,
        board_type: str = "overall",
        limit: int = 50,
        offset: int = 0,
        scenario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get leaderboard data.
        
        Args:
            board_type: Type of leaderboard (overall, daily, weekly, scenario)
            limit: Number of entries to return
            offset: Offset for pagination
            scenario_id: Scenario ID for scenario-specific leaderboard
            
        Returns:
            Leaderboard data
        """
        # Check cache
        cache_key = f"{board_type}_{scenario_id}" if scenario_id else board_type
        
        if (self.cache.get(cache_key) and 
            self.cache.get("last_update") and
            (datetime.utcnow() - self.cache["last_update"]).seconds < self.cache_ttl):
            
            cached = self.cache[cache_key]
            return {
                "entries": cached["entries"][offset:offset + limit],
                "total": len(cached["entries"]),
                "cached": True
            }
        
        # Query database
        with get_session() as session:
            query = session.query(
                Leaderboard,
                Agent,
                Result
            ).join(
                Result, Leaderboard.result_id == Result.id
            ).join(
                Agent, Result.agent_id == Agent.id
            )
            
            # Filter by board type
            if board_type == "scenario" and scenario_id:
                query = query.filter(
                    Leaderboard.board_type == f"scenario_{scenario_id}"
                )
            else:
                query = query.filter(Leaderboard.board_type == board_type)
            
            # Filter by date for daily/weekly
            if board_type == "daily":
                query = query.filter(
                    Leaderboard.board_date == datetime.utcnow().date()
                )
            elif board_type == "weekly":
                week_ago = datetime.utcnow() - timedelta(days=7)
                query = query.filter(
                    Leaderboard.board_date >= week_ago.date()
                )
            
            # Order by rank
            query = query.order_by(Leaderboard.rank)
            
            # Get total count
            total = query.count()
            
            # Apply pagination
            entries = query.offset(offset).limit(limit).all()
            
            # Format results
            leaderboard_entries = []
            for entry, agent, result in entries:
                leaderboard_entries.append({
                    "rank": entry.rank,
                    "agent_name": agent.name,
                    "agent_version": agent.version,
                    "agent_type": agent.agent_type,
                    "score": entry.score,
                    "metrics": entry.metrics,
                    "total_assessments": session.query(Assessment).filter_by(
                        agent_id=agent.id
                    ).count(),
                    "success_rate": result.success_rate,
                    "last_updated": entry.created_at.isoformat()
                })
            
            # Update cache
            self.cache[cache_key] = {
                "entries": leaderboard_entries,
                "total": total
            }
            self.cache["last_update"] = datetime.utcnow()
            
            return {
                "entries": leaderboard_entries,
                "total": total,
                "cached": False
            }
    
    async def get_agent_statistics(
        self,
        agent_id: str
    ) -> Dict[str, Any]:
        """
        Get detailed statistics for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent statistics
        """
        with get_session() as session:
            agent = session.query(Agent).filter_by(id=agent_id).first()
            
            if not agent:
                return {"error": "Agent not found"}
            
            # Get all assessments
            assessments = session.query(Assessment).filter_by(agent_id=agent_id).all()
            
            # Calculate statistics
            stats = {
                "agent_name": agent.name,
                "agent_version": agent.version,
                "total_assessments": len(assessments),
                "successful_assessments": sum(1 for a in assessments if a.passed),
                "failed_assessments": sum(1 for a in assessments if not a.passed),
                "success_rate": sum(1 for a in assessments if a.passed) / len(assessments) if assessments else 0,
                "average_execution_time": sum(a.execution_time or 0 for a in assessments) / len(assessments) if assessments else 0,
                "total_tokens_used": sum(a.token_usage or 0 for a in assessments),
                "scenarios_attempted": len(set(a.scenario_id for a in assessments))
            }
            
            # Get rankings
            results = session.query(Result).filter_by(agent_id=agent_id).all()
            
            if results:
                latest_result = max(results, key=lambda r: r.created_at)
                stats["current_rank_overall"] = latest_result.rank_overall
                stats["current_rank_daily"] = latest_result.rank_daily
                stats["best_score"] = max(r.overall_score for r in results)
                stats["average_score"] = sum(r.overall_score for r in results) / len(results)
            
            # Performance over time
            performance_timeline = []
            for assessment in sorted(assessments, key=lambda a: a.created_at)[-10:]:
                result = session.query(Result).filter_by(assessment_id=assessment.id).first()
                if result:
                    performance_timeline.append({
                        "date": assessment.created_at.isoformat(),
                        "score": result.overall_score,
                        "passed": assessment.passed
                    })
            
            stats["performance_timeline"] = performance_timeline
            
            return stats
    
    async def get_scenario_leaderboard(
        self,
        scenario_id: str
    ) -> Dict[str, Any]:
        """
        Get leaderboard for a specific scenario.
        
        Args:
            scenario_id: Scenario ID
            
        Returns:
            Scenario-specific leaderboard
        """
        with get_session() as session:
            # Get scenario info
            scenario = session.query(Scenario).filter_by(instance_id=scenario_id).first()
            
            if not scenario:
                return {"error": "Scenario not found"}
            
            # Get leaderboard
            leaderboard = await self.get_leaderboard(
                board_type="scenario",
                scenario_id=scenario_id
            )
            
            # Add scenario metadata
            leaderboard["scenario"] = {
                "instance_id": scenario.instance_id,
                "repo": scenario.repo,
                "difficulty": scenario.difficulty,
                "category": scenario.category,
                "attempt_count": scenario.attempt_count,
                "success_count": scenario.success_count,
                "success_rate": scenario.success_count / scenario.attempt_count if scenario.attempt_count > 0 else 0
            }
            
            return leaderboard
    
    async def get_trending_agents(
        self,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get agents with most improvement over time period.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of trending agents
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with get_session() as session:
            # Get results from time period
            recent_results = session.query(Result).filter(
                Result.created_at >= cutoff_date
            ).all()
            
            # Group by agent
            agent_scores = defaultdict(list)
            for result in recent_results:
                agent_scores[result.agent_id].append({
                    "score": result.overall_score,
                    "date": result.created_at
                })
            
            # Calculate improvement
            trending = []
            for agent_id, scores in agent_scores.items():
                if len(scores) < 2:
                    continue
                
                # Sort by date
                scores.sort(key=lambda x: x["date"])
                
                # Calculate improvement
                initial_score = scores[0]["score"]
                latest_score = scores[-1]["score"]
                improvement = latest_score - initial_score
                
                if improvement > 0:
                    agent = session.query(Agent).filter_by(id=agent_id).first()
                    if agent:
                        trending.append({
                            "agent_name": agent.name,
                            "agent_version": agent.version,
                            "improvement": improvement,
                            "initial_score": initial_score,
                            "latest_score": latest_score,
                            "assessment_count": len(scores)
                        })
            
            # Sort by improvement
            trending.sort(key=lambda x: x["improvement"], reverse=True)
            
            return trending[:10]  # Top 10 trending