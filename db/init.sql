SET NOCOUNT ON;
GO

IF DB_ID(N'OrdenesDB') IS NULL
BEGIN
    CREATE DATABASE OrdenesDB;
END
GO

USE OrdenesDB;
GO

IF OBJECT_ID(N'dbo.ordenes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ordenes (
        id       INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ordenes PRIMARY KEY,
        cliente  NVARCHAR(100)  NOT NULL,
        fecha    DATE           NOT NULL CONSTRAINT DF_ordenes_fecha DEFAULT (CAST(GETDATE() AS DATE)),
        estado   NVARCHAR(20)   NOT NULL CONSTRAINT DF_ordenes_estado DEFAULT (N'Pendiente'),
        total    DECIMAL(12,2)  NOT NULL CONSTRAINT DF_ordenes_total DEFAULT (0),
        CONSTRAINT CK_ordenes_estado CHECK (estado IN (N'Pendiente', N'Pagada', N'Anulada'))
    );
END
GO

IF OBJECT_ID(N'dbo.orden_detalle', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.orden_detalle (
        id               INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_orden_detalle PRIMARY KEY,
        orden_id         INT            NOT NULL,
        producto         NVARCHAR(100)  NOT NULL,
        cantidad         INT            NOT NULL,
        precio_unitario  DECIMAL(12,2)  NOT NULL,
        subtotal         DECIMAL(12,2)  NOT NULL,
        CONSTRAINT FK_detalle_orden FOREIGN KEY (orden_id)
            REFERENCES dbo.ordenes (id) ON DELETE CASCADE,
        CONSTRAINT CK_detalle_cantidad CHECK (cantidad > 0),
        CONSTRAINT CK_detalle_precio   CHECK (precio_unitario >= 0)
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ordenes)
BEGIN
    DECLARE @id INT;

    INSERT INTO dbo.ordenes (cliente, fecha, estado, total) VALUES (N'Maria Lopez', '2026-11-02', N'Pagada', 0);
    SET @id = SCOPE_IDENTITY();
    INSERT INTO dbo.orden_detalle (orden_id, producto, cantidad, precio_unitario, subtotal) VALUES
        (@id, N'Teclado mecanico',   1, 45.00, 45.00),
        (@id, N'Mouse inalambrico',  2, 15.50, 31.00);

    INSERT INTO dbo.ordenes (cliente, fecha, estado, total) VALUES (N'Carlos Mejia', '2026-11-03', N'Pendiente', 0);
    SET @id = SCOPE_IDENTITY();
    INSERT INTO dbo.orden_detalle (orden_id, producto, cantidad, precio_unitario, subtotal) VALUES
        (@id, N'Monitor 24 pulgadas', 2, 120.00, 240.00),
        (@id, N'Cable HDMI',          3,   6.00,  18.00),
        (@id, N'Soporte de monitor',  1,  22.50,  22.50);

    INSERT INTO dbo.ordenes (cliente, fecha, estado, total) VALUES (N'Ana Rodriguez', '2026-11-05', N'Pagada', 0);
    SET @id = SCOPE_IDENTITY();
    INSERT INTO dbo.orden_detalle (orden_id, producto, cantidad, precio_unitario, subtotal) VALUES
        (@id, N'Laptop 14 pulgadas', 1, 650.00, 650.00),
        (@id, N'Mochila para laptop', 1,  30.00,  30.00);

    INSERT INTO dbo.ordenes (cliente, fecha, estado, total) VALUES (N'Jose Hernandez', '2026-11-08', N'Anulada', 0);
    SET @id = SCOPE_IDENTITY();
    INSERT INTO dbo.orden_detalle (orden_id, producto, cantidad, precio_unitario, subtotal) VALUES
        (@id, N'Disco SSD 1TB',    2, 85.00, 170.00),
        (@id, N'Memoria RAM 16GB', 2, 48.00,  96.00);

    INSERT INTO dbo.ordenes (cliente, fecha, estado, total) VALUES (N'Lucia Fuentes', '2026-11-12', N'Pendiente', 0);
    SET @id = SCOPE_IDENTITY();
    INSERT INTO dbo.orden_detalle (orden_id, producto, cantidad, precio_unitario, subtotal) VALUES
        (@id, N'Impresora multifuncional', 1, 140.00, 140.00),
        (@id, N'Cartucho de tinta negra',  4,  18.00,  72.00),
        (@id, N'Resma de papel carta',     5,   5.50,  27.50);

    UPDATE o
       SET total = ISNULL((SELECT SUM(d.subtotal) FROM dbo.orden_detalle d WHERE d.orden_id = o.id), 0)
      FROM dbo.ordenes o;
END
GO

PRINT 'OrdenesDB lista.';
GO