import React from 'react';
import './LoadingSpinner.css';

const LoadingSpinner = ({ size = 'medium', className = '' }) => {
  const spinnerClasses = [
    'loading-spinner',
    `loading-spinner--${size}`,
    className
  ].filter(Boolean).join(' ');

  return (
    <div className={spinnerClasses}>
      <div className="spinner-ring">
        <div></div>
        <div></div>
        <div></div>
        <div></div>
      </div>
    </div>
  );
};

export default LoadingSpinner;
