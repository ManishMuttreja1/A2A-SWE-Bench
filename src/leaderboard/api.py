"""REST API for leaderboard access"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
import logging

from .leaderboard_service import LeaderboardService
from ..database import init_database

logger = logging.getLogger(__name__)


class LeaderboardAPI:
    """
    REST API for leaderboard access and queries.
    """
    
    def __init__(self, app: Optional[FastAPI] = None):
        self.app = app or FastAPI(
            title="SWE-bench Leaderboard API",
            version="1.0.0",
            description="Access leaderboard data for SWE-bench agents"
        )
        
        self.service = LeaderboardService()
        
        # Initialize database
        init_database()
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/api/leaderboard")
        async def get_leaderboard(
            board_type: str = Query("overall", description="Type of leaderboard"),
            limit: int = Query(50, ge=1, le=100, description="Number of entries"),
            offset: int = Query(0, ge=0, description="Offset for pagination"),
            scenario_id: Optional[str] = Query(None, description="Scenario ID for filtering")
        ):
            """Get leaderboard entries"""
            try:
                result = await self.service.get_leaderboard(
                    board_type=board_type,
                    limit=limit,
                    offset=offset,
                    scenario_id=scenario_id
                )
                return JSONResponse(content=result)
            except Exception as e:
                logger.error(f"Error getting leaderboard: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/leaderboard/agent/{agent_id}")
        async def get_agent_statistics(agent_id: str):
            """Get detailed statistics for an agent"""
            try:
                stats = await self.service.get_agent_statistics(agent_id)
                
                if "error" in stats:
                    raise HTTPException(status_code=404, detail=stats["error"])
                
                return JSONResponse(content=stats)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting agent statistics: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/leaderboard/scenario/{scenario_id}")
        async def get_scenario_leaderboard(scenario_id: str):
            """Get leaderboard for a specific scenario"""
            try:
                result = await self.service.get_scenario_leaderboard(scenario_id)
                
                if "error" in result:
                    raise HTTPException(status_code=404, detail=result["error"])
                
                return JSONResponse(content=result)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting scenario leaderboard: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/leaderboard/trending")
        async def get_trending_agents(
            days: int = Query(7, ge=1, le=30, description="Number of days to look back")
        ):
            """Get trending agents with most improvement"""
            try:
                trending = await self.service.get_trending_agents(days=days)
                return JSONResponse(content={"agents": trending, "days": days})
            except Exception as e:
                logger.error(f"Error getting trending agents: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/leaderboard/update/{assessment_id}")
        async def update_leaderboard(assessment_id: str):
            """Update leaderboard after a new assessment"""
            try:
                result = await self.service.update_leaderboard(assessment_id)
                
                if "error" in result:
                    raise HTTPException(status_code=404, detail=result["error"])
                
                return JSONResponse(content=result)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating leaderboard: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/leaderboard/stats")
        async def get_global_statistics():
            """Get global statistics across all agents"""
            try:
                from ..database import get_session, Agent, Assessment, Result, Scenario
                
                with get_session() as session:
                    stats = {
                        "total_agents": session.query(Agent).count(),
                        "total_assessments": session.query(Assessment).count(),
                        "total_scenarios": session.query(Scenario).count(),
                        "success_rate": 0,
                        "average_score": 0
                    }
                    
                    # Calculate success rate
                    assessments = session.query(Assessment).all()
                    if assessments:
                        stats["success_rate"] = sum(1 for a in assessments if a.passed) / len(assessments)
                    
                    # Calculate average score
                    results = session.query(Result).all()
                    if results:
                        stats["average_score"] = sum(r.overall_score for r in results) / len(results)
                    
                    # Get top performing agent
                    top_result = session.query(Result).order_by(
                        Result.overall_score.desc()
                    ).first()
                    
                    if top_result:
                        top_agent = session.query(Agent).filter_by(id=top_result.agent_id).first()
                        if top_agent:
                            stats["top_agent"] = {
                                "name": top_agent.name,
                                "version": top_agent.version,
                                "score": top_result.overall_score
                            }
                    
                    return JSONResponse(content=stats)
                    
            except Exception as e:
                logger.error(f"Error getting global statistics: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/leaderboard/export")
        async def export_leaderboard(
            board_type: str = Query("overall", description="Type of leaderboard"),
            format: str = Query("json", description="Export format (json, csv)")
        ):
            """Export leaderboard data"""
            try:
                # Get full leaderboard
                data = await self.service.get_leaderboard(
                    board_type=board_type,
                    limit=1000,
                    offset=0
                )
                
                if format == "csv":
                    import csv
                    import io
                    
                    output = io.StringIO()
                    
                    if data["entries"]:
                        writer = csv.DictWriter(
                            output,
                            fieldnames=data["entries"][0].keys()
                        )
                        writer.writeheader()
                        writer.writerows(data["entries"])
                    
                    return JSONResponse(
                        content=output.getvalue(),
                        media_type="text/csv",
                        headers={
                            "Content-Disposition": f"attachment; filename=leaderboard_{board_type}.csv"
                        }
                    )
                else:
                    return JSONResponse(content=data)
                    
            except Exception as e:
                logger.error(f"Error exporting leaderboard: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "service": "leaderboard-api"}
    
    def run(self, host: str = "0.0.0.0", port: int = 8080):
        """Run the API server"""
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)