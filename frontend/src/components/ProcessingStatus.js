import React, { useEffect, useRef } from 'react';
import './ProcessingStatus.css';

const EVENT_ICONS = {
    'tool_start': '🔧',
    'tool_complete': '✅',
    'tool_error': '❌',
    'reasoning': '💭',
    'memory_update': '🧠',
    'file_analysis': '📄',
    'search': '🔍',
    'iteration': '🔄',
    'thinking': '⏳',
    'connected': '🔗',
    'complete': '✨',
    'error': '❌',
    'info': '📌',
};

const ProcessingStatus = ({ events, isProcessing, title = "Agent Processing" }) => {
    const eventsEndRef = useRef(null);

    useEffect(() => {
        scrollToBottom();
    }, [events]);

    const scrollToBottom = () => {
        eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    const formatEventMessage = (event) => {
        const { event_type, data } = event;

        switch (event_type) {
            case 'file_analysis':
                return `Analyzing ${data.file_path || 'unknown'}`;
            case 'tool_start':
                return `Calling ${data.tool_name || 'unknown'}`;
            case 'tool_complete':
                return `${data.tool_name} completed: ${data.summary || ''}`;
            case 'tool_error':
                return `Error in ${data.tool_name}: ${data.message || ''}`;
            case 'reasoning':
                return data.message || '';
            case 'memory_update':
                return `${data.action || 'Updated'}: ${data.message || ''}`;
            case 'search':
                return `Searching: "${data.query || ''}"`;
            case 'iteration':
                return `Iteration ${data.current}/${data.max} (${data.files_analyzed} files)`;
            case 'thinking':
                return data.message || 'Processing...';
            default:
                return data.message || JSON.stringify(data);
        }
    };

    const getEventTime = (timestamp) => {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    if (events.length === 0 && !isProcessing) return null;

    return (
        <div className="processing-status">
            <div className="processing-status-header">
                <span className="agent-icon">🤖</span>
                <span>{title}</span>
            </div>

            <div className="processing-status-events">
                {events.map((event, index) => (
                    <div key={index} className={`event-item ${event.event_type}`}>
                        <div className="event-icon">
                            {EVENT_ICONS[event.event_type] || '📌'}
                        </div>
                        <div className="event-content">
                            <div className="event-message">{formatEventMessage(event)}</div>
                            {event.data.details && (
                                <div className="event-details">{event.data.details}</div>
                            )}
                        </div>
                        <div className="event-time">{getEventTime(event.timestamp)}</div>
                    </div>
                ))}
                <div ref={eventsEndRef} />
            </div>

            {isProcessing && (
                <div className="thinking-indicator">
                    <div className="pulse-dot"></div>
                    <span>Agent is working...</span>
                </div>
            )}
        </div>
    );
};

export default ProcessingStatus;
