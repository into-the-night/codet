import React from 'react';
import './StatusCard.css';

const StatusCard = ({ 
  icon, 
  title, 
  description, 
  status = 'default',
  className = '' 
}) => {
  const cardClasses = [
    'status-card',
    `status-card--${status}`,
    className
  ].filter(Boolean).join(' ');

  return (
    <div className={cardClasses}>
      <div className="status-card__icon">
        {icon}
      </div>
      <div className="status-card__content">
        <h3 className="status-card__title">{title}</h3>
        <p className="status-card__description">{description}</p>
      </div>
    </div>
  );
};

export default StatusCard;
