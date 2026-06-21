const express = require('express');
const cors = require('cors');
require('dotenv').config();

const app = express();

// 中間件
app.use(cors());
app.use(express.json());

// 路由 - 改為 /v1 前綴
app.use('/v1/auth', require('./routes/auth'));
app.use('/v1/user', require('./routes/user'));
app.use('/v1/billing', require('./routes/billing'));
app.use('/v1/preferences', require('./routes/preferences'));

// 健康檢查
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date() });
});

// 錯誤處理
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
