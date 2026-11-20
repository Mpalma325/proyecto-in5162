-- Fase 1 del diseño de instancias, revisión y escala: cuatro columnas del panel.
-- SQLite (D1) acepta una sola columna por ALTER TABLE.
-- Logro: de 0 a 1; vacío si no se corrigió con puntajes.
-- NotaModelo: la que propuso el modelo, antes de la revisión.
-- PorRevisar: corregida y sin mandar. Descartada: corrección descartada.
ALTER TABLE panel ADD COLUMN Logro REAL;
ALTER TABLE panel ADD COLUMN NotaModelo REAL;
ALTER TABLE panel ADD COLUMN PorRevisar INTEGER;
ALTER TABLE panel ADD COLUMN Descartada INTEGER;
