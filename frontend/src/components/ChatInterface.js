import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import './ChatInterface.css';
import LoadingSpinner from './LoadingSpinner';

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || !githubUrl.trim()) return;

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputValue,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setError('');

    try {
      const response = await axios.post('/api/chat', {
        question: inputValue,
        path: githubUrl.trim()
      });

      const aiMessage = {
        id: Date.now() + 1,
        type: 'ai',
        content: response.data.answer,
        analyzedFiles: response.data.analyzed_files,
        filesAnalyzedCount: response.data.files_analyzed_count,
        timestamp: response.data.timestamp
      };

      setMessages(prev => [...prev, aiMessage]);
    } catch (err) {
      const errorMessage = {
        id: Date.now() + 1,
        type: 'error',
        content: err.response?.data?.detail || 'Failed to get response from the AI',
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setError('');
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  return (
    <div className="chat-interface">
      <div className="chat-container">
        <div className="chat-header">
          <h2>Chat with Your GitHub Repository</h2>
          <p>Ask questions about your code and get intelligent answers</p>
        </div>

        <div className="chat-settings">
          <div className="setting-group github-url-group">
            <label htmlFor="github-url">GitHub Repository URL:</label>
            <input
              id="github-url"
              type="text"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              placeholder="https://github.com/username/repository"
              className="github-url-input"
            />
          </div>
        </div>

        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="welcome-message">
              <div className="welcome-icon">💬</div>
              <h3>Welcome to Code Chat!</h3>
              <p>{githubUrl ? 'Ask questions about your repository and get intelligent answers.' : 'Enter a GitHub repository URL above to start chatting with your code.'}</p>
              {githubUrl && (
                <div className="example-questions">
                  <h4>Example questions:</h4>
                  <ul>
                    <li>"How does the authentication system work?"</li>
                    <li>"What are the main API endpoints?"</li>
                    <li>"How is the database configured?"</li>
                    <li>"What testing frameworks are used?"</li>
                    <li>"How is error handling implemented?"</li>
                  </ul>
                </div>
              )}
            </div>
          )}

          {messages.map((message) => (
            <div key={message.id} className={`message ${message.type}`}>
              <div className="message-header">
                <span className="message-type">
                  {message.type === 'user' ? '👤 You' : 
                   message.type === 'ai' ? '🤖 AI Assistant' : 
                   '⚠️ Error'}
                </span>
                <span className="message-time">{formatTimestamp(message.timestamp)}</span>
              </div>
              <div className="message-content">
                {message.content}
              </div>
              {message.type === 'ai' && message.analyzedFiles && (
                <div className="message-meta">
                  <div className="analyzed-files">
                    <strong>Analyzed {message.filesAnalyzedCount} files:</strong>
                    <div className="file-list">
                      {message.analyzedFiles.slice(0, 5).map((file, index) => (
                        <span key={index} className="file-tag">{file}</span>
                      ))}
                      {message.analyzedFiles.length > 5 && (
                        <span className="file-tag more">+{message.analyzedFiles.length - 5} more</span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {isLoading && (
            <div className="message ai loading">
              <div className="message-header">
                <span className="message-type">🤖 AI Assistant</span>
                <span className="message-time">Now</span>
              </div>
              <div className="message-content">
                <LoadingSpinner size="small" />
                <span>Analyzing your codebase...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="chat-input-form">
          <div className="input-container">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={githubUrl ? "Ask a question about your code..." : "Please enter a GitHub URL first..."}
              className="chat-input"
              disabled={isLoading || !githubUrl.trim()}
            />
            <button 
              type="submit" 
              className="send-button"
              disabled={isLoading || !inputValue.trim() || !githubUrl.trim()}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        </form>

        {messages.length > 0 && (
          <div className="chat-actions">
            <button onClick={clearChat} className="clear-button">
              Clear Chat
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatInterface;
