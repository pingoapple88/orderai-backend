const express = require('express');
const router = express.Router();
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');

// Email 登入
router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    
    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password required' 
});
    }
    
    // 臨時實現 - 實際應查詢資料庫
    const token = jwt.sign(
      { email, id: 1 },
      process.env.JWT_SECRET || 'secret',
      { expiresIn: '7d' }
    );
    
    res.json({ token, user: { email } });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Email 註冊
router.post('/register', async (req, res) => {
  try {
    const { email, password } = req.body;
    
    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password required' 
});
    }
    
    res.json({ message: 'User registered successfully', email });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// LINE OAuth 回調
router.get('/line/callback', async (req, res) => {
  try {
    const { code } = req.query;
    
    if (!code) {
      return res.status(400).json({ error: 'Authorization code required' 
});
    }
    
    res.json({ message: 'LINE login successful' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Google OAuth 回調
router.get('/google/callback', async (req, res) => {
  try {
    const { code } = req.query;
    
    if (!code) {
      return res.status(400).json({ error: 'Authorization code required' 
});
    }
    
    res.json({ message: 'Google login successful' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Apple OAuth 回調
router.post('/apple/callback', async (req, res) => {
  try {
    const { code } = req.body;
    
    if (!code) {
      return res.status(400).json({ error: 'Authorization code required' 
});
    }
    
    res.json({ message: 'Apple login successful' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

