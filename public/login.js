const loginForm = document.getElementById('login-form');
const usernameInput = document.getElementById('username-input');
const passwordInput = document.getElementById('password-input');
const loginButton = document.getElementById('login-button');
const loginStatus = document.getElementById('login-status');

function setLoginStatus(message, isError = false) {
  loginStatus.textContent = message;
  loginStatus.className = isError ? 'login-status error-text' : 'login-status muted';
}

async function handleLogin(event) {
  event.preventDefault();
  loginButton.disabled = true;
  loginButton.textContent = 'Entering…';
  setLoginStatus('Checking…');

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: usernameInput.value.trim(),
        password: passwordInput.value,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Login failed.');
    }

    setLoginStatus('Opening…');
    window.location.assign('/');
  } catch (error) {
    passwordInput.value = '';
    setLoginStatus(error.message || 'Could not sign in.', true);
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = 'Enter workspace';
  }
}

loginForm.addEventListener('submit', handleLogin);
usernameInput.focus();
