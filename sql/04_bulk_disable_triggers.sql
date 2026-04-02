-- 大批量 COPY 前可暂时关闭业务触发器以提速（需足够权限）
-- 导入完成后务必执行 05_bulk_enable_triggers.sql
ALTER TABLE member DISABLE TRIGGER USER;
