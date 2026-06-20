const express = require('express');
const router = express.Router();

router.get('/records', (req, res) => {
  res.json({ records: [] });
});

router.post('/records', (req, res) => {
  res.json({ message: 'Billing record created' });
});

module.exports = router;


