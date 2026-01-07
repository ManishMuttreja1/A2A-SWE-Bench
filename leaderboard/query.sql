-- DuckDB query for SWE-bench A2A Leaderboard
-- This query calculates comprehensive scores for all agents

WITH agent_scores AS (
    SELECT 
        agent_name,
        agent_id,
        task_id,
        instance_id,
        
        -- Raw scores from evaluation
        correctness_score,
        process_score,
        efficiency_score,
        collaboration_score,
        understanding_score,
        adaptation_score,
        
        -- Weighted comprehensive score calculation
        (correctness_score * 0.35 + 
         process_score * 0.20 + 
         efficiency_score * 0.15 +
         collaboration_score * 0.15 +
         understanding_score * 0.10 +
         adaptation_score * 0.05) AS comprehensive_score,
         
        -- Additional metrics
        dialogue_turns,
        questions_asked,
        review_iterations,
        reproduction_verified,
        mutations_resisted,
        execution_time_seconds,
        actions_taken,
        
        -- Timestamps
        evaluation_timestamp
        
    FROM assessment_results
    WHERE evaluation_timestamp >= CURRENT_DATE - INTERVAL '30 days'
),

agent_aggregates AS (
    SELECT
        agent_name,
        agent_id,
        
        -- Overall performance
        AVG(comprehensive_score) AS avg_comprehensive_score,
        STDDEV(comprehensive_score) AS score_consistency,
        
        -- Category averages
        AVG(correctness_score) AS avg_correctness,
        AVG(process_score) AS avg_process,
        AVG(efficiency_score) AS avg_efficiency,
        AVG(collaboration_score) AS avg_collaboration,
        AVG(understanding_score) AS avg_understanding,
        AVG(adaptation_score) AS avg_adaptation,
        
        -- Task completion
        COUNT(DISTINCT task_id) AS tasks_attempted,
        COUNT(DISTINCT CASE WHEN correctness_score >= 0.7 THEN task_id END) AS tasks_passed,
        COUNT(DISTINCT CASE WHEN correctness_score = 1.0 THEN task_id END) AS perfect_solutions,
        
        -- Process quality metrics
        AVG(CASE WHEN reproduction_verified THEN 1 ELSE 0 END) AS reproduction_rate,
        AVG(dialogue_turns) AS avg_dialogue_turns,
        AVG(questions_asked) AS avg_questions,
        AVG(review_iterations) AS avg_review_iterations,
        
        -- Anti-contamination
        AVG(CASE WHEN mutations_resisted THEN 1 ELSE 0 END) AS mutation_resistance_rate,
        
        -- Efficiency metrics
        AVG(execution_time_seconds) AS avg_execution_time,
        AVG(actions_taken) AS avg_actions,
        AVG(efficiency_score / NULLIF(actions_taken, 0)) AS action_efficiency,
        
        -- Latest evaluation
        MAX(evaluation_timestamp) AS last_evaluated
        
    FROM agent_scores
    GROUP BY agent_name, agent_id
)

SELECT
    -- Ranking
    ROW_NUMBER() OVER (ORDER BY avg_comprehensive_score DESC) AS rank,
    DENSE_RANK() OVER (ORDER BY avg_comprehensive_score DESC) AS dense_rank,
    
    -- Agent identification
    agent_name,
    agent_id,
    
    -- Main score and grade
    ROUND(avg_comprehensive_score * 100, 2) AS score,
    CASE 
        WHEN avg_comprehensive_score >= 0.93 THEN 'A+'
        WHEN avg_comprehensive_score >= 0.90 THEN 'A'
        WHEN avg_comprehensive_score >= 0.87 THEN 'A-'
        WHEN avg_comprehensive_score >= 0.83 THEN 'B+'
        WHEN avg_comprehensive_score >= 0.80 THEN 'B'
        WHEN avg_comprehensive_score >= 0.77 THEN 'B-'
        WHEN avg_comprehensive_score >= 0.73 THEN 'C+'
        WHEN avg_comprehensive_score >= 0.70 THEN 'C'
        WHEN avg_comprehensive_score >= 0.67 THEN 'C-'
        WHEN avg_comprehensive_score >= 0.63 THEN 'D+'
        WHEN avg_comprehensive_score >= 0.60 THEN 'D'
        ELSE 'F'
    END AS grade,
    
    -- Performance breakdown
    ROUND(avg_correctness * 100, 1) AS correctness,
    ROUND(avg_process * 100, 1) AS process_quality,
    ROUND(avg_efficiency * 100, 1) AS efficiency,
    ROUND(avg_collaboration * 100, 1) AS collaboration,
    ROUND(avg_understanding * 100, 1) AS understanding,
    ROUND(avg_adaptation * 100, 1) AS adaptation,
    
    -- Task statistics
    tasks_attempted,
    tasks_passed,
    ROUND(tasks_passed::FLOAT / NULLIF(tasks_attempted, 0) * 100, 1) AS pass_rate,
    perfect_solutions,
    
    -- Quality indicators
    ROUND(reproduction_rate * 100, 1) AS reproduces_bugs_pct,
    ROUND(avg_dialogue_turns, 1) AS avg_dialogue,
    ROUND(avg_questions, 1) AS avg_questions,
    ROUND(avg_review_iterations, 1) AS avg_reviews,
    
    -- Anti-contamination score
    ROUND(mutation_resistance_rate * 100, 1) AS mutation_resistance_pct,
    
    -- Efficiency
    ROUND(avg_execution_time, 0) AS avg_time_seconds,
    ROUND(avg_actions, 0) AS avg_actions,
    ROUND(action_efficiency * 100, 1) AS action_efficiency_score,
    
    -- Consistency (lower is better)
    ROUND(score_consistency * 100, 2) AS score_variance,
    
    -- Trend (comparing last 7 days vs previous)
    CASE
        WHEN COUNT(*) FILTER (WHERE evaluation_timestamp >= CURRENT_DATE - INTERVAL '7 days') > 0
        THEN '📈'  -- Improving
        ELSE '📊'  -- Stable
    END AS trend,
    
    -- Last evaluation
    last_evaluated::DATE AS last_seen

FROM agent_aggregates

-- Minimum requirements for leaderboard
WHERE tasks_attempted >= 5  -- At least 5 tasks attempted

-- Sort by comprehensive score
ORDER BY avg_comprehensive_score DESC, score_consistency ASC

-- Limit to top agents
LIMIT 100;