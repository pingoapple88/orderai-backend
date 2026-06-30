-- ============================================================================
-- OrderAI 資料庫 Schema
-- ============================================================================
-- 版本: v2.0（PR-1b：金額整數化 + 多租戶 tenant_id）
-- 日期: 2026-06-30
-- 說明: 10 張表。金額一律以「幣別最小單位的整數」儲存（鐵律 7），
--       例：TWD 以「分」計，NT$390 = 39000；JPY 無小數則 = 整數日圓。
--       多租戶隔離鍵 tenant_id（鐵律 3）。
-- ============================================================================

-- ============================================================================
-- 0. tenants 表（租戶 / 店家，多市場）
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenants (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255),
  market VARCHAR(10) DEFAULT 'tw',           -- tw / jp / th / us
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 1. plans 表（定價方案）
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
-- 2. users 表（用戶基本信息）
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE,
  line_id VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255),
  avatar_url TEXT,
  phone VARCHAR(20),
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  tenant_id INTEGER REFERENCES tenants(id),  -- PR-1b：所屬租戶
  role VARCHAR(50) DEFAULT 'admin',          -- PR-1b：admin / staff
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
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);

-- ============================================================================
-- 3. user_preferences 表（用戶偏好設定）
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_preferences (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id INTEGER REFERENCES tenants(id),
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
-- 4. orders 表（訂單記錄）
-- ============================================================================
CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id INTEGER REFERENCES tenants(id),
  order_number VARCHAR(255) UNIQUE,
  customer_name VARCHAR(255),
  customer_phone VARCHAR(20),
  customer_email VARCHAR(255),
  total_amount INTEGER,                       -- 整數分位
  currency VARCHAR(3) DEFAULT 'TWD',
  status VARCHAR(50) DEFAULT 'pending',
  channel VARCHAR(50),
  source_image_url TEXT,
  ai_extraction_id INTEGER,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_id ON orders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- ============================================================================
-- 5. order_items 表（訂單明細）— 經 orders 關聯，不另加 tenant_id
-- ============================================================================
CREATE TABLE IF NOT EXISTS order_items (
  id SERIAL PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_name VARCHAR(255),
  quantity INTEGER,
  unit_price INTEGER,                         -- 整數分位
  subtotal INTEGER,                           -- 整數分位
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- ============================================================================
-- 6. billing_records 表（帳務記錄）
-- ============================================================================
CREATE TABLE IF NOT EXISTS billing_records (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id INTEGER REFERENCES tenants(id),
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
CREATE INDEX IF NOT EXISTS idx_billing_records_tenant_id ON billing_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_billing_records_status ON billing_records(status);

-- ============================================================================
-- 7. ai_extractions 表（AI 辨識結果）
-- ============================================================================
CREATE TABLE IF NOT EXISTS ai_extractions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id INTEGER REFERENCES tenants(id),
  image_url TEXT,
  extraction_result JSONB,
  confidence_score DECIMAL(3, 2),            -- 機率值，維持小數
  llm_provider VARCHAR(50),
  status VARCHAR(50) DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_user_id ON ai_extractions(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_tenant_id ON ai_extractions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_extractions_status ON ai_extractions(status);

-- ============================================================================
-- 8. ai_usage_logs 表（AI 配額使用日誌）
-- ============================================================================
CREATE TABLE IF NOT EXISTS ai_usage_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id INTEGER REFERENCES tenants(id),
  extraction_id INTEGER REFERENCES ai_extractions(id),
  usage_date DATE,
  usage_count INTEGER DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_user_id ON ai_usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_tenant_id ON ai_usage_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_usage_date ON ai_usage_logs(usage_date);

-- ============================================================================
-- 9. audit_logs 表（操作日誌）
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  tenant_id INTEGER REFERENCES tenants(id),
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
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- ============================================================================
-- 初始化資料
-- ============================================================================
-- plans 金額為整數分位（TWD：NT$390 = 39000、NT$790 = 79000）
INSERT INTO plans (name, monthly_price, currency, ai_extraction_limit, team_member_limit, features)
VALUES
  ('lite', 39000, 'TWD', 300, 1, '{"ai_extraction": true, "basic_reporting": true}'),
  ('pro', 79000, 'TWD', -1, -1, '{"ai_extraction": true, "advanced_reporting": true, "team_collaboration": true}')
ON CONFLICT (name) DO NOTHING;
