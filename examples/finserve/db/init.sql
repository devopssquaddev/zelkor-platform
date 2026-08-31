-- FinServe AI Multi-Tenant Portfolio Database Seeding
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    account_number VARCHAR(20) NOT NULL,
    client_name VARCHAR(100) NOT NULL,
    ssn VARCHAR(20) NOT NULL,
    balance NUMERIC(15, 2) NOT NULL,
    risk_profile VARCHAR(20) NOT NULL,
    holdings JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_portfolios_tenant_id ON portfolios(tenant_id);

ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY;

-- Seed Bank_Alpha Portfolios
INSERT INTO portfolios (tenant_id, account_number, client_name, ssn, balance, risk_profile, holdings)
VALUES
('Bank_Alpha', 'ACC-ALPHA-001', 'Alice Johnson', '111-22-3333', 250000.00, 'Moderate', '{"AAPL": 40, "MSFT": 30, "GOOGL": 30}'::jsonb),
('Bank_Alpha', 'ACC-ALPHA-002', 'Bob Smith', '222-33-4444', 500000.00, 'Aggressive', '{"NVDA": 50, "TSLA": 30, "AMZN": 20}'::jsonb)
ON CONFLICT DO NOTHING;

-- Seed Bank_Beta Portfolios
INSERT INTO portfolios (tenant_id, account_number, client_name, ssn, balance, risk_profile, holdings)
VALUES
('Bank_Beta', 'ACC-BETA-001', 'Charlie Brown', '333-44-5555', 750000.00, 'Conservative', '{"BND": 60, "VTI": 30, "GLD": 10}'::jsonb),
('Bank_Beta', 'ACC-BETA-002', 'Diana Prince', '444-55-6666', 1200000.00, 'Moderate', '{"SPY": 50, "QQQ": 30, "CASH": 20}'::jsonb)
ON CONFLICT DO NOTHING;

-- Demo table policy uses the GUC CE postgres MCP already SET LOCAL. Not platform Auto-RLS.
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS portfolios_tenant_isolation ON portfolios;
CREATE POLICY portfolios_tenant_isolation ON portfolios
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
