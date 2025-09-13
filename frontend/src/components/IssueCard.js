import React, { useState } from 'react';
import './IssueCard.css';
import Toast from './Toast';
import { formatIssueForAI, copyToClipboard as copyTextToClipboard } from '../utils/reportFormatter';
import { getIssueLinkFromIssue } from '../utils/githubIssueHelper';

// Helper functions for code snippet handling
const getFileLanguage = (filePath) => {
  const extension = filePath.split('.').pop()?.toLowerCase();
  const languageMap = {
    'py': 'python',
    'js': 'javascript',
    'jsx': 'javascript',
    'ts': 'typescript',
    'tsx': 'typescript',
    'java': 'java',
    'go': 'go',
    'rs': 'rust',
    'cpp': 'cpp',
    'c': 'c',
    'cs': 'csharp',
    'php': 'php',
    'rb': 'ruby',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',
    'sh': 'bash',
    'bash': 'bash',
    'yaml': 'yaml',
    'yml': 'yaml',
    'json': 'json',
    'xml': 'xml',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'less': 'less',
    'sql': 'sql',
    'md': 'markdown',
    'dockerfile': 'dockerfile'
  };
  return languageMap[extension] || 'text';
};

const formatCodeSnippet = (snippet) => {
  if (!snippet) return '';
  
  // The snippet comes from backend with line numbers in format "1234|    code" or "1234|>>> code"
  // We'll preserve the line numbers and highlight the problematic line
  return snippet.split('\n').map(line => {
    // Match format: "1234|    code" or "1234|>>> code"
    const match = line.match(/^\s*(\d+)\|\s*(>>>\s*)?(.*)$/);
    if (match) {
      const [, lineNum, highlight, code] = match;
      if (highlight) {
        // This is the problematic line - we'll mark it for special styling
        return `>>> ${lineNum.padStart(4)} | ${code}`;
      } else {
        return `    ${lineNum.padStart(4)} | ${code}`;
      }
    }
    return line;
  }).join('\n');
};

const formatCodeSnippetWithHighlighting = (snippet) => {
  if (!snippet) return '';
  
  // Create JSX elements for better highlighting
  return snippet.split('\n').map((line, index) => {
    // Match format: "1234|    code" or "1234|>>> code"
    const match = line.match(/^\s*(\d+)\|\s*(>>>\s*)?(.*)$/);
    if (match) {
      const [, lineNum, highlight, code] = match;
      const isProblematic = !!highlight;
      
      return (
        <div key={index} className={`code-line ${isProblematic ? 'problematic-line' : ''}`}>
          <span className="line-number">{lineNum.padStart(4)}</span>
          <span className="line-separator">|</span>
          <span className="line-content">{code}</span>
        </div>
      );
    }
    return (
      <div key={index} className="code-line">
        <span className="line-content">{line}</span>
      </div>
    );
  });
};

const copyToClipboard = async (text, setToast) => {
  try {
    await navigator.clipboard.writeText(text);
    setToast({ message: 'Code copied to clipboard!', type: 'success' });
  } catch (err) {
    console.error('Failed to copy code: ', err);
    // Fallback for older browsers
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
    setToast({ message: 'Code copied to clipboard!', type: 'success' });
  }
};

const IssueCard = ({ issue, githubRepo = null }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [toast, setToast] = useState(null);
  const [copyStatus, setCopyStatus] = useState('idle'); // 'idle', 'copying', 'success', 'error'

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return 'var(--error)';
      case 'high': return 'var(--warning)';
      case 'medium': return 'var(--text-secondary)';
      case 'low': return 'var(--text-muted)';
      default: return 'var(--text-muted)';
    }
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'critical': return '🚨';
      case 'high': return '⚠️';
      case 'medium': return 'ℹ️';
      case 'low': return '💡';
      default: return '📝';
    }
  };

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'security': return '🔒';
      case 'performance': return '⚡';
      case 'duplication': return '🔄';
      case 'complexity': return '📊';
      case 'testing': return '🧪';
      case 'documentation': return '📚';
      case 'style': return '🎨';
      case 'maintainability': return '🔧';
      default: return '📝';
    }
  };

  const getDetectionMethod = (issue) => {
    if (issue.metadata && issue.metadata.ai_detected) {
      return {
        icon: '🤖',
        label: 'AI Detected',
        color: 'var(--accent-primary)'
      };
    }
    return {
      icon: '🔍',
      label: 'Static Analysis',
      color: 'var(--text-secondary)'
    };
  };

  const handleCopyIssue = async (e) => {
    e.stopPropagation(); // Prevent expanding/collapsing the card
    
    setCopyStatus('copying');
    try {
      const formattedIssue = formatIssueForAI(issue);
      const success = await copyTextToClipboard(formattedIssue);
      
      if (success) {
        setCopyStatus('success');
        setToast({ message: 'Issue copied to clipboard!', type: 'success' });
        // Reset status after 3 seconds
        setTimeout(() => setCopyStatus('idle'), 3000);
      } else {
        setCopyStatus('error');
        setToast({ message: 'Failed to copy issue', type: 'error' });
        setTimeout(() => setCopyStatus('idle'), 3000);
      }
    } catch (error) {
      console.error('Failed to copy issue:', error);
      setCopyStatus('error');
      setToast({ message: 'Failed to copy issue', type: 'error' });
      setTimeout(() => setCopyStatus('idle'), 3000);
    }
  };

  const handleCreateGitHubIssue = (e) => {
    e.stopPropagation(); // Prevent expanding/collapsing the card
    
    if (!githubRepo) {
      setToast({ message: 'GitHub repository not configured', type: 'error' });
      return;
    }

    try {
      const { owner, repo } = githubRepo;
      const issueUrl = getIssueLinkFromIssue(issue, owner, repo, {
        defaultLabels: ['code-quality', 'automated'],
        defaultAssignees: [] // You can add default assignees here if needed
      });
      
      // Open in new tab
      window.open(issueUrl, '_blank', 'noopener,noreferrer');
      setToast({ message: 'Opening GitHub issue creation page...', type: 'success' });
    } catch (error) {
      console.error('Failed to create GitHub issue URL:', error);
      setToast({ message: 'Failed to create GitHub issue', type: 'error' });
    }
  };

  return (
    <div className="issue-card">
      <div 
        className="issue-card__header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="issue-card__main">
          <div className="issue-card__severity">
            <span className="severity-icon">{getSeverityIcon(issue.severity)}</span>
            <span 
              className="severity-badge"
              style={{ color: getSeverityColor(issue.severity) }}
            >
              {issue.severity.toUpperCase()}
            </span>
          </div>
          
          <div className="issue-card__content">
            <h3 className="issue-card__title">{issue.title}</h3>
            <p className="issue-card__description">{issue.description}</p>
            <div className="issue-card__meta">
              <span className="category">
                {getCategoryIcon(issue.category)} {issue.category}
              </span>
              <span 
                className="detection-method"
                style={{ color: getDetectionMethod(issue).color }}
              >
                {getDetectionMethod(issue).icon} {getDetectionMethod(issue).label}
              </span>
              <span className="file-path">
                {issue.file_path}
                {issue.line_number && `:${issue.line_number}`}
              </span>
            </div>
          </div>
        </div>
        
        <div className="issue-card__actions">
          <button 
            className="github-issue-button"
            onClick={handleCreateGitHubIssue}
            title="Create GitHub issue for this problem"
            disabled={!githubRepo}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M9 19C-1 19 -1 5 9 5C20 5 20 19 9 19Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M9 9H9.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M9 13H9.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M9 17H9.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <button 
            className={`copy-issue-button ${copyStatus}`}
            onClick={handleCopyIssue}
            disabled={copyStatus === 'copying'}
            title="Copy issue for AI tools (Cursor, Claude, etc.)"
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
          </button>
          <button 
            className={`expand-button ${isExpanded ? 'expanded' : ''}`}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 9L12 15L18 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
      
      {isExpanded && (
        <div className="issue-card__details">
          {issue.suggestion && (
            <div className="suggestion">
              <h4 className="suggestion-title">💡 Suggestion</h4>
              <p className="suggestion-text">{issue.suggestion}</p>
            </div>
          )}
          
          {issue.code_snippet && (
            <div className="code-snippet">
              <div className="code-snippet-header">
                <h4 className="code-snippet-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 3H5C3.89543 3 3 3.89543 3 5V19C3 20.1046 3.89543 21 5 21H19C20.1046 21 21 20.1046 21 19V16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M21 3H12L8 7L12 11H21V3Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Code Snippet
                </h4>
                <button 
                  className="copy-button"
                  onClick={() => copyToClipboard(issue.code_snippet, setToast)}
                  title="Copy code to clipboard"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" strokeWidth="2" fill="none"/>
                    <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" stroke="currentColor" strokeWidth="2" fill="none"/>
                  </svg>
                </button>
              </div>
              <div className="code-snippet-container">
                <pre className="code-snippet-content">
                  <code className={`language-${getFileLanguage(issue.file_path)}`}>
                    {formatCodeSnippetWithHighlighting(issue.code_snippet)}
                  </code>
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
      
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
};

export default IssueCard;
