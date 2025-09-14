import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Existing API functions
export const analyzeGitHubRepo = async (githubUrl) => {
  const response = await api.post('/api/analyze-github', {
    github_url: githubUrl,
  });
  return response.data;
};

export const getAnalysisResults = async (analysisId) => {
  const response = await api.get(`/api/report/${analysisId}`);
  return response.data;
};

export const chatWithCodebase = async (question, path, configPath = null) => {
  const response = await api.post('/api/chat', {
    question,
    path,
    config_path: configPath,
  });
  return response.data;
};

// Codebase indexing API functions
export const indexCodebase = async (path, collectionName = 'codebase', batchSize = 100) => {
  const response = await api.post('/api/index', {
    path,
    collection_name: collectionName,
    batch_size: batchSize,
  });
  return response.data;
};

export const searchCodebase = async (query, searchType = 'hybrid', limit = 10, collectionName = 'codebase') => {
  const response = await api.post('/api/search', {
    query,
    search_type: searchType,
    limit,
    collection_name: collectionName,
  });
  return response.data;
};

export const getIndexStatistics = async (collectionName = 'codebase') => {
  const response = await api.get(`/api/index/stats/${collectionName}`);
  return response.data;
};

export default api;
