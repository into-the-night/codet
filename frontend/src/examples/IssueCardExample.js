import React from 'react';
import IssueCard from '../components/IssueCard';

// Example usage of IssueCard with GitHub integration
const IssueCardExample = () => {
  // Example issue data
  const exampleIssue = {
    title: "Unused variable 'temp'",
    description: "The variable 'temp' is declared but never used in the function.",
    severity: "medium",
    category: "style",
    file_path: "src/utils/helper.js",
    line_number: 42,
    suggestion: "Remove the unused variable or use it in your logic.",
    code_snippet: "   42|    const temp = calculateValue();\n   43|    return result;\n   44|    // temp is never used",
    metadata: {
      ai_detected: true,
      confidence: 0.95
    }
  };

  // GitHub repository configuration
  const githubRepo = {
    owner: "your-username", // Replace with actual GitHub username/org
    repo: "your-repository" // Replace with actual repository name
  };

  return (
    <div style={{ padding: '20px', maxWidth: '800px' }}>
      <h2>Issue Card with GitHub Integration</h2>
      <p>Click the GitHub button (📋) to create a GitHub issue for this problem.</p>
      
      <IssueCard 
        issue={exampleIssue} 
        githubRepo={githubRepo}
      />
      
      <div style={{ marginTop: '20px', padding: '16px', backgroundColor: '#f6f8fa', borderRadius: '8px' }}>
        <h3>Usage Instructions:</h3>
        <ol>
          <li>Configure the <code>githubRepo</code> prop with your repository details</li>
          <li>Pass the <code>githubRepo</code> object to each <code>IssueCard</code> component</li>
          <li>Click the GitHub button to create a new issue with pre-filled content</li>
        </ol>
        
        <h4>GitHub Repository Configuration:</h4>
        <pre style={{ backgroundColor: '#fff', padding: '12px', borderRadius: '4px', overflow: 'auto' }}>
{`const githubRepo = {
  owner: "your-username",    // GitHub username or organization
  repo: "your-repository"    // Repository name
};`}
        </pre>
      </div>
    </div>
  );
};

export default IssueCardExample;
