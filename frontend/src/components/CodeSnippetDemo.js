import React, { useState } from 'react';
import IssueCard from './IssueCard';
import './CodeSnippetDemo.css';

const CodeSnippetDemo = () => {
  const [selectedDemo, setSelectedDemo] = useState('security');

  const demoSnippets = {
    security: {
      title: 'SQL Injection Vulnerability',
      description: 'User input is directly concatenated into SQL query without proper sanitization.',
      severity: 'critical',
      category: 'security',
      file_path: 'src/database/user_service.py',
      line_number: 45,
      suggestion: 'Use parameterized queries or an ORM to prevent SQL injection attacks.',
      code_snippet: `  42|    def get_user_by_email(self, email):
  43|        query = "SELECT * FROM users WHERE email = '" + email + "'"
  44|        cursor = self.connection.cursor()
  45|>>> 46|        result = cursor.execute(query)
  46|        return cursor.fetchone()
  47|    def update_user_profile(self, user_id, data):
  48|        # More code here...`
    },
    performance: {
      title: 'Inefficient Loop with String Concatenation',
      description: 'String concatenation in a loop creates multiple string objects, causing performance issues.',
      severity: 'medium',
      category: 'performance',
      file_path: 'src/utils/text_processor.js',
      line_number: 23,
      suggestion: 'Use array.join() or template literals for better performance.',
      code_snippet: `  20|    function processText(items) {
  21|        let result = "";
  22|        for (let i = 0; i < items.length; i++) {
  23|>>> 24|            result += items[i] + " ";
  24|        }
  25|        return result.trim();
  26|    }`
    },
    duplication: {
      title: 'Duplicate Code Block',
      description: 'Similar validation logic is repeated in multiple places.',
      severity: 'low',
      category: 'duplication',
      file_path: 'src/validators/user_validator.py',
      line_number: 15,
      suggestion: 'Extract common validation logic into a reusable function.',
      code_snippet: `  12|    def validate_email(self, email):
  13|        if not email or '@' not in email:
  14|            return False
  15|>>> 16|        if len(email) < 5 or len(email) > 100:
  16|            return False
  17|        return True
  18|    def validate_username(self, username):
  19|        if not username or len(username) < 3:
  20|            return False
  21|        if len(username) > 50:
  22|            return False
  23|        return True`
    },
    complexity: {
      title: 'High Cyclomatic Complexity',
      description: 'Function has too many conditional branches, making it hard to test and maintain.',
      severity: 'high',
      category: 'complexity',
      file_path: 'src/processors/data_processor.py',
      line_number: 67,
      suggestion: 'Break down this function into smaller, more focused functions.',
      code_snippet: `  64|    def process_data(self, data, options):
  65|        if data is None:
  66|            return None
  67|>>> 68|        if options.get('validate') and not self.validate(data):
  68|            if options.get('strict'):
  69|                raise ValueError("Invalid data")
  70|            else:
  71|                data = self.clean_data(data)
  72|        if options.get('transform'):
  73|            data = self.transform(data)
  74|        if options.get('cache'):
  75|            self.cache.set(data.id, data)
  76|        return data`
    }
  };

  return (
    <div className="code-snippet-demo">
      <div className="demo-header">
        <h2>Enhanced Code Snippet Display</h2>
        <p>Click on different demo types to see how code snippets are displayed with proper formatting, syntax highlighting, and line highlighting.</p>
      </div>

      <div className="demo-controls">
        {Object.keys(demoSnippets).map((key) => (
          <button
            key={key}
            className={`demo-button ${selectedDemo === key ? 'active' : ''}`}
            onClick={() => setSelectedDemo(key)}
          >
            {key.charAt(0).toUpperCase() + key.slice(1)}
          </button>
        ))}
      </div>

      <div className="demo-content">
        <IssueCard issue={demoSnippets[selectedDemo]} />
      </div>

      <div className="demo-features">
        <h3>Features Demonstrated:</h3>
        <ul>
          <li>✅ <strong>Line Numbers:</strong> Clear line numbering for easy reference</li>
          <li>✅ <strong>Problematic Line Highlighting:</strong> The issue line is highlighted with a warning icon and red border</li>
          <li>✅ <strong>Syntax Highlighting:</strong> Language-specific colors for better readability</li>
          <li>✅ <strong>Copy to Clipboard:</strong> Click the copy button to copy code snippets</li>
          <li>✅ <strong>Responsive Design:</strong> Works well on mobile and desktop</li>
          <li>✅ <strong>Expandable Cards:</strong> Click to expand and see full details</li>
        </ul>
      </div>
    </div>
  );
};

export default CodeSnippetDemo;
