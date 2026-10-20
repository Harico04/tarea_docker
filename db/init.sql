CREATE TABLE IF NOT EXISTS imagenes (
    fecha       DATE PRIMARY KEY,
    imagen_url  TEXT NOT NULL,
    autor       TEXT,
    descripcion TEXT
);
