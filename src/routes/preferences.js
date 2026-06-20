const express = require('express');
const router = express.Router();

router.get('/', (req, res) => {
  res.json({ preferences: { language: 'zh-TW', theme: 'light' } });
});

router.put('/', (req, res) => {
  res.json({ message: 'Preferences updated' });
});

module.exports = router;

