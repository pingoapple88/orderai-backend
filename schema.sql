-- ============================================================================
-- OrderAI 資料庫 Schema
-- ============================================================================
-- 版本: v3.0（migration 0004 Option A 租戶模型重構）
-- 日期: 2026-07-12
-- 說明: 14 張表。migration 0004 將 tenants 改名為 stores，新增 companies/dealers/customers。
--       金額一律以「幣別最小單位的整數」儲存（鐵律 7），
--       例：TWD 以「分」計，NT$390 = 39000；JPY 無小數則 = 整數日圓。
--       多租戶隔離鍵 store_id（鐵律 3）。
-- ============================================================================

-- ============================================================================
-- 0. companies 表（公司 / 集團）
-- ============================================================================
CREATE TABLE IF NOT EXISTS companies (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 1. dealers 表（經銷商 / 分公司）
-- ============================================================================
CREATE TABLE IF NOT EXISTS dealers (
  id SERIAL PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  code VARCHAR(255) UNIQUE,  -- 推薦碼（model 有；非破壞 ADD，既有列先留 NULL）
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dealers_company_id ON dealers(company_id);

-- ============================================================================
-- 2. customers 表（客戶）
-- ============================================================================
CREATE TABLE IF NOT EXISTS customers (
  id SERIAL PRIMARY KEY,
  dealer_id INTEGER NOT NULL REFERENCES dealers(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  store_id INTEGER,     -- model 有（FK→stores）；stores 在本檔後段建，故此處不加 REFERENCES 避免前向依賴
  line_user_id TEXT,    -- model 有；LINE 下單客戶綁定（WO-002）
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customers_dealer_id ON customers(dealer_id);

-- ============================================================================
-- 3. stores 表（店家，原 tenants 改名）
-- ============================================================================
CREATE TABLE IF NOT EXISTS stores (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255),
  market VARCHAR(10) DEFAULT 'tw',           -- tw / jp / th / us
  industry_type VARCHAR(20) DEFAULT 'ecom',  -- 0003：ecom / beauty / food（美業架構預留）
  company_id INTEGER REFERENCES companies(id),            -- 0004：所屬母公司（可空）
  referred_by_dealer_id INTEGER REFERENCES dealers(id),   -- 0004：推薦經銷商（可空）
  plan VARCHAR(50) DEFAULT 'lite',                         -- 0004：方案
  line_channel_id VARCHAR(64),                            -- 0004：LINE channel（secret 只在 ENV）
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 4. plans 表（定價方案）
-- ============================================================================
CREATE TABLE IF NOT EXISTS plans (
  id SERIAL PRIMARY KEY,
  name VARCHAR(50) UNIQUE NOT NULL,
  monthly_price INTEGER NOT NULL,            -- 整數分位（最小幣別單位）
  currency VARCHAR(3) DEFAULT 'TWD',
  ai_extraction_limit INTEGER,
  team_member_limit INTEGER,
  features JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 5. users 表（用戶基本信息）
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE,
  line_id VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255),
  avatar_url TEXT,
  picture_url TEXT,                          -- 0004：LINE 頭像（auth.py 建 user 時寫入）
  phone VARCHAR(20),
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  store_id INTEGER REFERENCES stores(id),  -- migration 0004：所屬店家
  role VARCHAR(50) DEFAULT 'admin',          -- admin / staff
  ai_usage_count INTEGER DEFAULT 0,
  ai_usage_reset_date DATE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT TRUE,
  deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_line_id ON users(line_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_plan_id ON users(plan_id);
CREATE INDEX IF NOT EXISTS idx_users_store_id ON users(store_id);

-- ============================================================================
-- 6. user_preferences 表（用戶偏好設定）
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_preferences (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  store_id INTEGER REFERENCES stores(id),
  language VARCHAR(10) DEFAULT 'zh-TW',
  theme VARCHAR(10) DEFAULT 'light',
  notifications_enabled BOOLEAN DEFAULT TRUE,
  email_notifications BOOLEAN DEFAULT TRUE,
  line_notifications BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id)
);

-- ============================================================================
-- 7. orders 表（訂單記錄）
-- ============================================================================
CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  store_id INTEGER REFERENCES stores(id),
  order_number VARCHAR(255) UNIQUE,
  customer_name VARCHAR(255),
  customer_phone VARCHAR(20),
  customer_email VARCHAR(255),
  total_cents INTEGER,                       -- 整數分位（改名：total_amount → total_cents）
  currency VARCHAR(3) DEFAULT 'TWD',
  status VARCHAR(50) DEFAULT 'pending',
  channel VARCHAR(50),
  source_image_url TEXT,
  ai_extraction_id INTEGER,
  customer_id INTEGER REFERENCES customers(id),   -- 0004：下單客戶（AI 抄單建/綁）
  ai_extraction JSONB,                             -- 0004：AI 解析結果快照
  confirmed_at TIMESTAMP WITH TIME ZONE,           -- 0004：確認時間
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_store_id ON orders(store_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- ============================================================================
-- 8. order_items 表（訂單明細）— 經 orders 關聯，不另加 store_id
-- ============================================================================
CREATE TABLE IF NOT EXISTS order_items (
  id SERIAL PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_name VARCHAR(255),
  quantity INTEGER,
  unit VARCHAR(20) DEFAULT '個',             -- 0004：單位（個/份/隻…）
  unit_price_cents INTEGER,                  -- 整數分位（改名：unit_price → unit_price_cents）
  subtotal_cents INTEGER,                    -- 整數分位（改名：subtotal → subtotal_cents）
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- ============================================================================
-- 9. billing_records 表（帳務記錄）
-- ============================================================================
CREATE TABLE IF NOT EXISTS billing_records (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  store_id INTEGER REFERENCES stores(id),
  order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
  amount INTEGER,                             -- 整數分位
  currency VARCHAR(3) DEFAULT 'TWD',
  status VARCHAR(50) DEFAULT 'pending',
  payment_method VARCHAR(50),
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_billing_records_user_id ON billing_records(user_id);
CREATE INDEX IF NOT EXISTS idx_billing_records_store_id ON billing_records(store_id);
CREATE INDEX IF NOT EXISTS idx_billing_records_status ON billing_records(status);

-- ============================================================================
-- 10. ai_extractions 表（AI 辨識結果）
-- ============================================================================
CREATE TABLE IF NOT EXISTS ai_extractions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  store_id INTEGER REFERENCES stores(id),
  image_url TEXT,
  extraction_result JSONB,
  confidence_score DECIMAL(3, 2),            -- 機率值，維持小數
  llm_provider VARCHAR(50),
  status VARCHAR(50) DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_user_id ON ai_extractions(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_store_id ON ai_extractions(store_id);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_status ON ai_extractions(status);

-- ============================================================================
-- 11. ai_usage_logs 表（AI 配額使用日誌）
-- ============================================================================
CREATE TABLE IF NOT EXISTS ai_usage_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  store_id INTEGER REFERENCES stores(id),
  extraction_id INTEGER REFERENCES ai_extractions(id),
  usage_date DATE,
  usage_count INTEGER DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_user_id ON ai_usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_store_id ON ai_usage_logs(store_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_usage_date ON ai_usage_logs(usage_date);

-- ============================================================================
-- 12. audit_logs 表（操作日誌）
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  store_id INTEGER REFERENCES stores(id),
  action VARCHAR(255),
  resource_type VARCHAR(50),
  resource_id INTEGER,
  old_value JSONB,
  new_value JSONB,
  ip_address VARCHAR(45),
  user_agent TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_store_id ON audit_logs(store_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- ============================================================================
-- 13. system_settings 表（全域可調參數，禁止寫死）
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_settings (
  key VARCHAR(100) PRIMARY KEY,
  value TEXT,
  description TEXT,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 初始化資料
-- ============================================================================
-- plans 金額為整數分位（TWD：NT$390 = 39000、NT$790 = 79000）
INSERT INTO plans (name, monthly_price, currency, ai_extraction_limit, team_member_limit, features)
VALUES
  ('lite', 39000, 'TWD', 300, 1, '{"ai_extraction": true, "basic_reporting": true}'),
  ('pro', 79000, 'TWD', -1, -1, '{"ai_extraction": true, "advanced_reporting": true, "team_collaboration": true}')
ON CONFLICT (name) DO NOTHING;

INSERT INTO system_settings (key, value, description) VALUES
  ('ai_soft_limit_pro', '10000', 'Pro 方案每月 AI 解析軟上限'),
  ('pre_filter_regex', '(\+\s*\d+|＋\s*\d+|#下單|要買|預購|下單|訂購|\d+\s*份|\d+\s*個|\d+\s*組)', '接單意圖預檢正則；不符者略過 LLM'),
  ('polling_interval_minutes', '30', '付款未回調主動輪詢間隔（分）')
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- migration 0004：以 store_id 為首的複合索引（20 萬租戶查詢效能）
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_orders_store_user ON orders(store_id, user_id);
CREATE INDEX IF NOT EXISTS idx_orders_store_status ON orders(store_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_store_created ON orders(store_id, created_at);
CREATE INDEX IF NOT EXISTS idx_billing_store_status ON billing_records(store_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_store_status ON ai_extractions(store_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_usage_store_date ON ai_usage_logs(store_id, usage_date);
CREATE INDEX IF NOT EXISTS idx_audit_store_created ON audit_logs(store_id, created_at);
