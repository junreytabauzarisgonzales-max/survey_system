// Keep the public website independent of the local survey engine and its API.
if (import.meta.env.MODE === 'app' || import.meta.env.MODE === 'hosted') {
  import('./SurveyApp.jsx');
} else {
  import('./site/main.jsx');
}
