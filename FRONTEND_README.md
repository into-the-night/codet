# codet Frontend

A futuristic, minimalistic frontend for the codet code quality analysis tool, featuring a black and white design inspired by Cursor and Vercel's UI.

## Features

- **Modern UI Design**: Clean, minimalistic black and white interface with smooth animations
- **GitHub Integration**: Clone and analyze any public GitHub repository by URL
- **Real-time Analysis**: Live progress tracking during repository analysis
- **Comprehensive Results**: Detailed analysis dashboard with metrics, issues, and recommendations
- **Responsive Design**: Works seamlessly on desktop and mobile devices

## Tech Stack

- **React 18**: Modern React with hooks and functional components
- **React Router**: Client-side routing for navigation
- **Axios**: HTTP client for API communication
- **CSS3**: Custom CSS with CSS variables for theming
- **Modern JavaScript**: ES6+ features and async/await

## Design System

### Color Palette
- **Primary Background**: `#000000` (Pure black)
- **Secondary Background**: `#111111` (Dark gray)
- **Tertiary Background**: `#1a1a1a` (Lighter dark gray)
- **Primary Text**: `#ffffff` (Pure white)
- **Secondary Text**: `#a0a0a0` (Light gray)
- **Muted Text**: `#666666` (Medium gray)
- **Accent**: `#ffffff` (White for highlights)
- **Success**: `#00ff88` (Bright green)
- **Warning**: `#ffaa00` (Orange)
- **Error**: `#ff4444` (Red)

### Typography
- **Primary Font**: Inter (system font fallback)
- **Monospace**: JetBrains Mono (for code)

### Components
- **Button**: Multiple variants (primary, secondary, ghost) with hover effects
- **Input**: Clean input fields with focus states
- **Cards**: Glass morphism effect with subtle borders
- **Loading Spinner**: Animated ring spinner
- **Status Cards**: Feature cards with icons and descriptions
- **Issue Cards**: Expandable cards for code issues
- **Metric Cards**: Dashboard metrics with progress bars

## Getting Started

### Prerequisites
- Node.js 16+ 
- npm or yarn
- Backend server running on port 8000

### Installation

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Start the development server:
```bash
npm start
```

3. Open [http://localhost:3000](http://localhost:3000) in your browser

### Development Script

Use the provided development script to start both backend and frontend:

```bash
./start_dev.sh
```

This will start:
- Backend API on http://localhost:8000
- Frontend on http://localhost:3000
- API documentation on http://localhost:8000/docs

## Usage

1. **Enter GitHub URL**: Paste any public GitHub repository URL
2. **Start Analysis**: Click "Start Analysis" to clone and analyze the repository
3. **View Results**: Browse through the analysis dashboard with:
   - Quality score and metrics
   - Issues categorized by severity
   - Detailed issue descriptions with suggestions
   - Code snippets and file locations

## API Integration

The frontend communicates with the backend through these endpoints:

- `POST /api/analyze-github`: Clone and analyze a GitHub repository
- `GET /api/report/{analysis_id}`: Get analysis results
- `GET /api/health`: Health check

## File Structure

```
frontend/src/
├── components/
│   ├── GitHubAnalyzer.js      # Main analysis input component
│   ├── AnalysisDashboard.js   # Results dashboard
│   ├── Header.js              # Navigation header
│   ├── Button.js              # Reusable button component
│   ├── Input.js               # Reusable input component
│   ├── LoadingSpinner.js      # Loading animation
│   ├── StatusCard.js          # Feature status cards
│   ├── IssueCard.js           # Issue display cards
│   └── MetricCard.js          # Dashboard metrics
├── App.js                     # Main app component
├── App.css                    # Global styles and utilities
└── index.css                  # Base styles and CSS variables
```

## Customization

### Theming
Modify CSS variables in `index.css` to customize colors:

```css
:root {
  --bg-primary: #000000;
  --text-primary: #ffffff;
  --accent-primary: #ffffff;
  /* ... other variables */
}
```

### Adding New Components
Follow the existing component pattern:
1. Create component file with `.js` extension
2. Create corresponding `.css` file
3. Import and use in parent components
4. Follow the design system guidelines

## Performance

- **Lazy Loading**: Components are loaded as needed
- **Optimized Animations**: CSS transitions with `cubic-bezier` easing
- **Efficient Rendering**: React best practices for performance
- **Minimal Bundle**: Only necessary dependencies included

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Contributing

1. Follow the existing code style and patterns
2. Use semantic HTML and accessible components
3. Test on multiple screen sizes
4. Ensure smooth animations and transitions
5. Maintain the minimalistic design aesthetic

## License

Same as the main codet project.
