import React from 'react';
import './MetricCard.css';

const MetricCard = ({ 
  title, 
  value, 
  max, 
  unit = '', 
  status = 'default',
  className = '' 
}) => {
  const cardClasses = [
    'metric-card',
    `metric-card--${status}`,
    className
  ].filter(Boolean).join(' ');

  const getStatusColor = (status) => {
    switch (status) {
      case 'success': return 'var(--success)';
      case 'warning': return 'var(--warning)';
      case 'error': return 'var(--error)';
      default: return 'var(--text-primary)';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'success': return '✅';
      case 'warning': return '⚠️';
      case 'error': return '❌';
      default: return '📊';
    }
  };

  const percentage = max ? Math.round((value / max) * 100) : null;

  return (
    <div className={cardClasses}>
      <div className="metric-card__header">
        <h3 className="metric-card__title">{title}</h3>
        <span className="metric-card__icon">{getStatusIcon(status)}</span>
      </div>
      
      <div className="metric-card__value">
        <span 
          className="value-number"
          style={{ color: getStatusColor(status) }}
        >
          {value}
        </span>
        {unit && <span className="value-unit">{unit}</span>}
      </div>
      
      {percentage !== null && (
        <div className="metric-card__progress">
          <div className="progress-bar">
            <div 
              className="progress-fill"
              style={{ 
                width: `${percentage}%`,
                backgroundColor: getStatusColor(status)
              }}
            />
          </div>
          <span className="progress-text">{percentage}%</span>
        </div>
      )}
    </div>
  );
};

export default MetricCard;
