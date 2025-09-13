import React from 'react';
import './Button.css';

const Button = ({ 
  children, 
  onClick, 
  disabled = false, 
  variant = 'primary', 
  size = 'medium',
  className = '',
  type = 'button',
  ...props 
}) => {
  const buttonClasses = [
    'button',
    `button--${variant}`,
    `button--${size}`,
    className
  ].filter(Boolean).join(' ');

  return (
    <button
      type={type}
      className={buttonClasses}
      onClick={onClick}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
};

export default Button;
