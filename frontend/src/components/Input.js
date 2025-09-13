import React from 'react';
import './Input.css';

const Input = ({ 
  type = 'text',
  placeholder = '',
  value = '',
  onChange,
  onKeyPress,
  disabled = false,
  className = '',
  ...props 
}) => {
  const inputClasses = [
    'input',
    className
  ].filter(Boolean).join(' ');

  return (
    <input
      type={type}
      className={inputClasses}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      onKeyPress={onKeyPress}
      disabled={disabled}
      {...props}
    />
  );
};

export default Input;
