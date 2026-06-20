const express = require('express');
const router = express.Router();

router.get('/profile', (req, res) => {
  res.json({ user: { id: 1, email: 'user@example.com' } });
});

router.put('/profile', (req, res) => {
  res.json({ message: 'Profile updated' });
});

module.exports = router;


