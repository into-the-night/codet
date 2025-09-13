import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import './AnalysisDashboard.css';
import StatusCard from './StatusCard';
import IssueCard from './IssueCard';
import MetricCard from './MetricCard';
import LoadingSpinner from './LoadingSpinner';
import { formatReportForAI, copyToClipboard } from '../utils/reportFormatter';

const AnalysisDashboard = () => {
  const { analysisId } = useParams();
  const navigate = useNavigate();
  const [analysisData, setAnalysisData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copyStatus, setCopyStatus] = useState('idle'); // 'idle', 'copying', 'success', 'error'

  useEffect(() => {
    fetchAnalysisData();
  }, [analysisId]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchAnalysisData = async () => {
    try {
      const response = await axios.get(`/api/report/${analysisId}`);
      setAnalysisData(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load analysis results');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyReport = async () => {
    if (!analysisData) return;
    
    setCopyStatus('copying');
    try {
      const formattedReport = formatReportForAI(analysisData);
      const success = await copyToClipboard(formattedReport);
      
      if (success) {
        setCopyStatus('success');
        // Reset status after 3 seconds
        setTimeout(() => setCopyStatus('idle'), 3000);
      } else {
        setCopyStatus('error');
        setTimeout(() => setCopyStatus('idle'), 3000);
      }
    } catch (error) {
      console.error('Failed to copy report:', error);
      setCopyStatus('error');
      setTimeout(() => setCopyStatus('idle'), 3000);
    }
  };

  if (loading) {
    return (
      <div className="analysis-dashboard">
        <div className="container">
          <div className="loading-container">
            <LoadingSpinner size="large" />
            <p className="loading-text">Loading analysis results...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analysis-dashboard">
        <div className="container">
          <div className="error-container">
            <div className="error-icon">⚠️</div>
            <h2 className="error-title">Analysis Failed</h2>
            <p className="error-message">{error}</p>
            <button 
              className="retry-button"
              onClick={() => navigate('/')}
            >
              Start New Analysis
            </button>
          </div>
        </div>
      </div>
    );
  }

  const { summary, issues } = analysisData;
  const criticalIssues = issues.filter(issue => issue.severity === 'critical');

  // Extract GitHub repo information from the summary or project_path if available
  const extractGithubRepo = () => {
    // Check both github_url and project_path
    const githubUrl = summary?.github_url || analysisData?.project_path;
    
    if (githubUrl && typeof githubUrl === 'string') {
      // Fix common typos (missing slash after https:)
      const fixedUrl = githubUrl.replace(/^https:\/(?!\/)/, 'https://');
      
      // Extract owner and repo from GitHub URL
      // Example: https://github.com/owner/repo -> { owner: 'owner', repo: 'repo' }
      const match = fixedUrl.match(/github\.com\/([^\/]+)\/([^\/]+)/);
      if (match) {
        return {
          owner: match[1],
          repo: match[2]
        };
      }
    }
    return null;
  };

  const githubRepo = extractGithubRepo();

  // Debug logging
  console.log('Analysis Data:', analysisData);
  console.log('Summary:', summary);
  console.log('GitHub URL from summary:', summary?.github_url);
  console.log('Project Path:', analysisData?.project_path);
  console.log('Extracted GitHub Repo:', githubRepo);

  return (
    <div className="analysis-dashboard">
      <div className="container">
        <div className="dashboard-header">
          <button 
            className="back-button"
            onClick={() => navigate('/')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M19 12H5M12 19L5 12L12 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Back to Analysis
          </button>
          <div className="header-content">
            <h1 className="dashboard-title">Analysis Results</h1>
            <p className="dashboard-subtitle">
              Repository: <code>{analysisData.project_path}</code>
            </p>
          </div>
          <button 
            className={`copy-report-button ${copyStatus}`}
            onClick={handleCopyReport}
            disabled={copyStatus === 'copying'}
            title="Copy report for AI tools (Cursor, Claude, etc.)"
          >
            {copyStatus === 'copying' && (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="spinning">
                <path d="M12 2V6M12 18V22M4.93 4.93L7.76 7.76M16.24 16.24L19.07 19.07M2 12H6M18 12H22M4.93 19.07L7.76 16.24M16.24 7.76L19.07 4.93" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
            {copyStatus === 'success' && (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M20 6L9 17L4 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
            {copyStatus === 'error' && (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
            {copyStatus === 'idle' && (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" strokeWidth="2" fill="none"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="2" fill="none"/>
              </svg>
            )}
            <span className="button-text">
              {copyStatus === 'copying' && 'Copying...'}
              {copyStatus === 'success' && 'Copied!'}
              {copyStatus === 'error' && 'Failed'}
              {copyStatus === 'idle' && 'Copy Report'}
            </span>
          </button>
        </div>

        <div className="metrics-grid">
          <MetricCard
            title="Quality Score"
            value={summary.quality_score.toFixed(2) || 0}
            max={100}
            unit="%"
            status={summary.quality_score >= 80 ? 'success' : summary.quality_score >= 60 ? 'warning' : 'error'}
          />
          <MetricCard
            title="Total Issues"
            value={issues.length}
            status={issues.length === 0 ? 'success' : issues.length < 10 ? 'warning' : 'error'}
          />
          <MetricCard
            title="Critical Issues"
            value={criticalIssues.length}
            status={criticalIssues.length === 0 ? 'success' : 'error'}
          />
          <MetricCard
            title="Files Analyzed"
            value={summary.files_analyzed || 0}
            status="default"
          />
        </div>


        <div className="issues-list">
          <h2 className="section-title">All Issues</h2>
          {issues.length === 0 ? (
            <div className="no-issues">
              <div className="no-issues-icon">✅</div>
              <h3>No Issues Found</h3>
              <p>Your code looks great! No quality issues were detected.</p>
            </div>
          ) : (
            <div className="issues-grid">
              {issues.map((issue, index) => (
                <IssueCard key={index} issue={issue} githubRepo={githubRepo} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AnalysisDashboard;
