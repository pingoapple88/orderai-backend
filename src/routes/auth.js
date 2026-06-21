const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const router = express.Router();

const LINE_CHANNEL_ID = process.env.LINE_CHANNEL_ID;
const LINE_CHANNEL_SECRET = process.env.LINE_CHANNEL_SECRET;
const FRONTEND_URL = process.env.FRONTEND_URL || 'https://orderai.merchcore.ai';
const JWT_SECRET = process.env.JWT_SECRET;

// LINE 登入重定向端點
router.get('/line', (req, res ) => {
  const redirectUri = encodeURIComponent(
    `${FRONTEND_URL}/api/auth/line/callback`
  );
  const state = Math.random().toString(36).substring(7);
  
  const lineAuthUrl = 
    `https://access.line.me/oauth2/v2.1/authorize?` +
    `response_type=code&` +
    `client_id=${LINE_CHANNEL_ID}&` +
    `redirect_uri=${redirectUri}&` +
    `state=${state}&` +
    `scope=profile%20openid&` +
    `prompt=consent`;
  
  res.redirect(lineAuthUrl );
});

// LINE 登入回調端點
router.get('/line/callback', async (req, res) => {
  const { code, state } = req.query;
  
  if (!code) {
    return res.status(400).json({ error: 'Missing authorization code' });
  }
  
  try {
    const tokenResponse = await axios.post(
      'https://api.line.me/oauth2/v2.1/token',
      new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: `${FRONTEND_URL}/api/auth/line/callback`,
        client_id: LINE_CHANNEL_ID,
        client_secret: LINE_CHANNEL_SECRET,
      } ).toString(),
      {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      }
    );
    
    const { access_token, id_token } = tokenResponse.data;
    
    const userResponse = await axios.get(
      'https://api.line.me/v2/profile',
      {
        headers: {
          Authorization: `Bearer ${access_token}`,
        },
      }
     );
    
    const { userId, displayName, pictureUrl, statusMessage } = userResponse.data;
    
    const jwtToken = jwt.sign(
      {
        userId,
        displayName,
        pictureUrl,
        statusMessage,
        provider: 'line',
        lineUserId: userId,
      },
      JWT_SECRET,
      { expiresIn: '7d' }
    );
    
    res.json({
  token: jwtToken,
  provider: 'line',
  displayName: displayName
});

const frontendCallbackUrl = new 
URL(`${FRONTEND_URL}/api/auth/line/callback`);
    frontendCallbackUrl.searchParams.append('token', jwtToken);
    frontendCallbackUrl.searchParams.append('provider', 'line');
    frontendCallbackUrl.searchParams.append('displayName', displayName);
    
    res.redirect(frontendCallbackUrl.toString());
  } catch (error) {
    console.error('LINE OAuth error:', error.response?.data || error.message);
    res.status(500).json({ 
      error: 'Authentication failed',
      details: error.message 
    });
  }
});

router.get('/google', (req, res) => {
  res.json({ message: 'Google login coming soon' });
});

router.get('/google/callback', (req, res) => {
  res.json({ message: 'Google callback coming soon' });
});

router.get('/apple', (req, res) => {
  res.json({ message: 'Apple login coming soon' });
});

router.post('/apple/callback', (req, res) => {
  res.json({ message: 'Apple callback coming soon' });
});

router.post('/email', (req, res) => {
  res.json({ message: 'Email login coming soon' });
});

router.post('/email/register', (req, res) => {
  res.json({ message: 'Email registration coming soon' });
});

module.exports = router;
