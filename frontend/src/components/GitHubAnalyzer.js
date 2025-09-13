import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import './GitHubAnalyzer.css';
import Button from './Button';
import Input from './Input';
import LoadingSpinner from './LoadingSpinner';
import StatusCard from './StatusCard';

const GitHubAnalyzer = () => {
  const [githubUrl, setGithubUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const navigate = useNavigate();

  const validateGitHubUrl = (url) => {
    const githubRegex = /^https:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(?:\/.*)?$/;
    return githubRegex.test(url);
  };

  const handleAnalyze = async () => {
    if (!githubUrl.trim()) {
      setError('Please enter a GitHub repository URL');
      return;
    }

    if (!validateGitHubUrl(githubUrl)) {
      setError('Please enter a valid GitHub repository URL');
      return;
    }

    setError('');
    setIsAnalyzing(true);
    setAnalysisProgress(0);

    let progressInterval;
    try {
      // Simulate progress updates
      progressInterval = setInterval(() => {
        setAnalysisProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + Math.random() * 15;
        });
      }, 500);

      // Call the backend API to clone and analyze
      const response = await axios.post('/api/analyze-github', {
        github_url: githubUrl,
        languages: ['python', 'javascript', 'typescript', 'java', 'go', 'rust']
      });

      clearInterval(progressInterval);
      setAnalysisProgress(100);

      // Navigate to analysis results
      setTimeout(() => {
        navigate(`/analysis/${response.data.analysis_id}`);
      }, 1000);

    } catch (err) {
      clearInterval(progressInterval);
      setError(err.response?.data?.detail || 'Failed to analyze repository. Please try again.');
      setIsAnalyzing(false);
      setAnalysisProgress(0);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !isAnalyzing) {
      handleAnalyze();
    }
  };

  return (
    <div className="github-analyzer">
      <div className="container-sm">
        <div className="analyzer-content">
          <div className="hero-section">
            <h1 className="hero-title">
              Analyze Your
              <span className="gradient-text"> Code Quality</span>
            </h1>
            <p className="hero-description">
              Enter a GitHub repository URL to get comprehensive code quality analysis, 
              security insights, and improvement recommendations.
            </p>
          </div>

          <div className="analyzer-card glass">
            <div className="card-header">
              <h2 className="card-title">Repository Analysis</h2>
              <p className="card-description">
                We'll clone your repository and analyze it for code quality, security, and best practices.
              </p>
            </div>

            <div className="input-section">
              <Input
                type="url"
                placeholder="https://github.com/username/repository"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={isAnalyzing}
                className="github-input"
              />
              
              {error && (
                <div className="error-message">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                    <line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" strokeWidth="2"/>
                    <line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" strokeWidth="2"/>
                  </svg>
                  {error}
                </div>
              )}
            </div>

            <div className="action-section">
              <Button
                onClick={handleAnalyze}
                disabled={isAnalyzing || !githubUrl.trim()}
                className="analyze-button"
                size="large"
              >
                {isAnalyzing ? (
                  <>
                    <LoadingSpinner size="small" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M9 12L11 14L15 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" strokeWidth="2"/>
                    </svg>
                    Start Analysis
                  </>
                )}
              </Button>
            </div>

            {isAnalyzing && (
              <div className="progress-section">
                <div className="progress-bar">
                  <div 
                    className="progress-fill" 
                    style={{ width: `${analysisProgress}%` }}
                  />
                </div>
                <div className="progress-text">
                  {analysisProgress < 30 && "Cloning repository..."}
                  {analysisProgress >= 30 && analysisProgress < 60 && "Scanning files..."}
                  {analysisProgress >= 60 && analysisProgress < 90 && "Analyzing code quality..."}
                  {analysisProgress >= 90 && "Finalizing results..."}
                </div>
              </div>
            )}
          </div>

          <div className="features-section">
            <h3 className="features-title">What We Analyze</h3>
            <div className="features-grid">
              <StatusCard
                icon="🔒"
                title="Security Vulnerabilities"
                description="Detect potential security issues and vulnerabilities in your code"
              />
              <StatusCard
                icon="⚡"
                title="Performance Issues"
                description="Identify performance bottlenecks and optimization opportunities"
              />
              <StatusCard
                icon="🔄"
                title="Code Duplication"
                description="Find duplicated code blocks and suggest refactoring opportunities"
              />
              <StatusCard
                icon="📊"
                title="Complexity Analysis"
                description="Measure code complexity and maintainability metrics"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GitHubAnalyzer;
