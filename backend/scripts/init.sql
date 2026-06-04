-- Multi-Agent Customer Chat Database Schema
-- Minimal, efficient schema for production use

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Chat sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'closed', 'escalated')),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sender VARCHAR(100) NOT NULL CHECK (sender IN ('user', 'router', 'faq', 'support', 'refund', 'guardrails', 'escalation', 'assistant')),
    content TEXT NOT NULL,
    message_type VARCHAR(50) DEFAULT 'text' CHECK (message_type IN ('text', 'system', 'error')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Note: the FAQ knowledge base and the refund policy are NOT stored here.
-- They are editable markdown documents under backend/knowledge/ (refund_policy.md,
-- faqs.md), read live by the agents via app/knowledge.py.

-- Escalation tracking
CREATE TABLE escalations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'assigned', 'resolved')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_to VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for performance
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_escalations_session_id ON escalations(session_id);
CREATE INDEX idx_escalations_status ON escalations(status);

-- ============================================================================
-- E-COMMERCE REFUND DOMAIN: mock CRM (customers + orders), policy, audit log
-- ============================================================================

-- Mock CRM: customer profiles
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    tier VARCHAR(50) NOT NULL DEFAULT 'standard' CHECK (tier IN ('standard', 'premium', 'vip')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Order history
CREATE TABLE orders (
    id VARCHAR(20) PRIMARY KEY,                       -- human-friendly id, e.g. ORD-1001
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    item VARCHAR(255) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'delivered'
        CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled', 'returned')),
    is_final_sale BOOLEAN NOT NULL DEFAULT FALSE,
    already_refunded BOOLEAN NOT NULL DEFAULT FALSE,
    order_date DATE NOT NULL
);

-- Audit log of refund decisions made by the agent
CREATE TABLE refund_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id VARCHAR(20) REFERENCES orders(id) ON DELETE SET NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('approved', 'denied', 'escalated')),
    amount NUMERIC(10, 2),
    reason TEXT NOT NULL,
    resolution VARCHAR(20) CHECK (resolution IN ('approved', 'rejected')),
    resolved_by VARCHAR(255),
    resolution_note TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Per-turn reasoning log powering the admin dashboard
CREATE TABLE agent_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    user_message TEXT NOT NULL,
    handling_agent VARCHAR(50),
    router_intent VARCHAR(100),
    router_reasoning TEXT,
    refund_decision VARCHAR(20),
    guardrails_score NUMERIC(4, 2),
    tool_trace JSONB DEFAULT '[]'::jsonb,
    final_response TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_refund_decisions_order_id ON refund_decisions(order_id);
CREATE INDEX idx_refund_decisions_session_id ON refund_decisions(session_id);
CREATE INDEX idx_agent_logs_session_id ON agent_logs(session_id);
CREATE INDEX idx_agent_logs_created_at ON agent_logs(created_at);

-- ~15 mock customers
INSERT INTO customers (name, email, tier) VALUES
('Alice Johnson',  'alice.johnson@example.com',  'premium'),   -- 1
('Bob Smith',      'bob.smith@example.com',      'standard'),  -- 2
('Carol Martinez', 'carol.martinez@example.com', 'vip'),       -- 3
('David Lee',      'david.lee@example.com',      'standard'),  -- 4
('Emma Wilson',    'emma.wilson@example.com',    'premium'),   -- 5
('Frank Garcia',   'frank.garcia@example.com',   'standard'),  -- 6
('Grace Kim',      'grace.kim@example.com',      'standard'),  -- 7
('Henry Brown',    'henry.brown@example.com',    'premium'),   -- 8
('Isla Davis',     'isla.davis@example.com',     'standard'),  -- 9
('Jack Taylor',    'jack.taylor@example.com',    'vip'),       -- 10
('Karen White',    'karen.white@example.com',    'standard'),  -- 11
('Liam Moore',     'liam.moore@example.com',     'standard'),  -- 12
('Mia Anderson',   'mia.anderson@example.com',   'premium'),   -- 13
('Noah Thomas',    'noah.thomas@example.com',    'standard'),  -- 14
('Olivia Jackson', 'olivia.jackson@example.com', 'standard');  -- 15

-- Orders with deliberate edge cases. Reference date for the window is mid-2026.
INSERT INTO orders (id, customer_id, item, amount, status, is_final_sale, already_refunded, order_date) VALUES
('ORD-1001', 1,  'Wireless Headphones',        129.99, 'delivered', FALSE, FALSE, '2026-05-25'),  -- approvable
('ORD-1002', 1,  'USB-C Cable',                 19.99, 'delivered', FALSE, FALSE, '2026-05-26'),  -- approvable
('ORD-1003', 2,  'Gaming Laptop',             1299.00, 'delivered', FALSE, FALSE, '2026-05-20'),  -- escalate (>$500)
('ORD-1004', 2,  'Clearance Mouse Pad',         12.50, 'delivered', TRUE,  FALSE, '2026-05-22'),  -- deny (final sale)
('ORD-1005', 3,  'Designer Handbag',           850.00, 'delivered', FALSE, FALSE, '2026-05-15'),  -- escalate (>$500)
('ORD-1006', 3,  'Silk Scarf',                  75.00, 'delivered', FALSE, TRUE,  '2026-05-10'),  -- deny (already refunded)
('ORD-1007', 4,  '4K Monitor',                 399.99, 'delivered', FALSE, FALSE, '2026-01-15'),  -- deny (outside 30-day window)
('ORD-1008', 4,  'HDMI Cable',                  14.99, 'delivered', FALSE, FALSE, '2026-05-30'),  -- approvable
('ORD-1009', 5,  'Espresso Machine',           249.00, 'delivered', FALSE, FALSE, '2026-05-28'),  -- approvable
('ORD-1010', 5,  'Coffee Beans (Clearance)',    22.00, 'delivered', TRUE,  FALSE, '2026-05-29'),  -- deny (final sale)
('ORD-1011', 6,  'Office Chair',               189.00, 'delivered', FALSE, FALSE, '2026-05-18'),  -- approvable
('ORD-1012', 6,  'Standing Desk',              540.00, 'delivered', FALSE, FALSE, '2026-05-19'),  -- escalate (>$500)
('ORD-1013', 7,  'Running Shoes',               89.99, 'shipped',   FALSE, FALSE, '2026-05-31'),  -- approvable (shipped)
('ORD-1014', 7,  'Gift Card',                   50.00, 'delivered', TRUE,  FALSE, '2026-05-31'),  -- deny (final sale gift card)
('ORD-1015', 8,  'Smartwatch',                 299.00, 'delivered', FALSE, FALSE, '2026-04-01'),  -- deny (outside window)
('ORD-1016', 8,  'Watch Band',                  29.00, 'delivered', FALSE, FALSE, '2026-05-27'),  -- approvable
('ORD-1017', 9,  'Mechanical Keyboard',        119.00, 'processing',FALSE, FALSE, '2026-06-01'),  -- not refundable (processing)
('ORD-1018', 10, 'OLED TV',                   1799.00, 'delivered', FALSE, FALSE, '2026-05-21'),  -- escalate (>$500)
('ORD-1019', 10, 'Soundbar',                   199.00, 'delivered', FALSE, TRUE,  '2026-05-12'),  -- deny (already refunded)
('ORD-1020', 11, 'Backpack',                     65.00, 'cancelled', FALSE, FALSE, '2026-05-24'),  -- deny (cancelled)
('ORD-1021', 12, 'Bluetooth Speaker',           79.00, 'delivered', FALSE, FALSE, '2026-05-23'),  -- approvable
('ORD-1022', 13, 'Camera Lens',                620.00, 'delivered', FALSE, FALSE, '2026-05-17'),  -- escalate (>$500)
('ORD-1023', 14, 'Phone Case',                  18.00, 'delivered', FALSE, FALSE, '2026-05-29'),  -- approvable
('ORD-1024', 15, 'Winter Jacket',              159.00, 'returned',  FALSE, TRUE,  '2026-02-10'),  -- deny (already refunded + old)
('ORD-1025', 9,  'Desk Lamp',                    34.00, 'delivered', FALSE, FALSE, '2026-05-30');  -- approvable

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at
CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column(); 