"""Compatibilidad de arranque para el selector de inventarios.

Python carga sitecustomize automáticamente cuando el directorio del proyecto
forma parte de sys.path. Aprovechamos ese punto para reemplazar únicamente la
pantalla de selección de inventarios, sin depender de las rutas locales de
cada PC.
"""


def _instalar_selector_portable():
    try:
        import main
    except Exception as error:
        print(f"[sitecustomize] No se pudo preparar el selector: {error}")
        return

    def construir_opciones_documentos(parent):
        documentos = []

        for documento in main.obtener_documentos_cache():
            if not isinstance(documento, dict):
                continue

            nombre = main.limpiar_texto(documento.get("nombre"))

            if not nombre:
                ruta = main.limpiar_texto(documento.get("ruta")).replace("\\", "/")
                if ruta:
                    nombre = ruta.rsplit("/", 1)[-1].strip()

            if not nombre:
                nombre = f"Inventario #{documento.get('id', '')}".strip()

            copia = dict(documento)
            copia["nombre"] = nombre
            documentos.append(copia)

        documentos.sort(
            key=lambda documento: main.limpiar_texto(
                documento.get("nombre")
            ).casefold()
        )

        main.ttk.Label(
            parent,
            text="Seleccioná el inventario",
            font=("Segoe UI", 15, "bold"),
        ).pack(pady=(20, 5))

        main.ttk.Label(
            parent,
            text="Cada archivo Word administra su propio stock.",
            foreground=main.COLOR_TEXTO_SECUNDARIO,
        ).pack(pady=(0, 18))

        cont = main.tk.Frame(
            parent,
            bg=main.COLOR_FONDO,
        )
        cont.pack(
            fill="both",
            expand=True,
            padx=40,
            pady=10,
        )

        if not documentos:
            main.ttk.Label(
                cont,
                text="No se encontraron inventarios en la base de datos.",
                font=("Segoe UI", 11),
            ).pack(pady=40)
            return

        columnas = 2

        for i, documento in enumerate(documentos):
            nombre = main.limpiar_texto(documento.get("nombre"))

            tarjeta = main.tk.Frame(
                cont,
                bg=main.COLOR_PANEL,
                highlightbackground=main.COLOR_BORDE,
                highlightthickness=1,
                padx=18,
                pady=15,
                cursor="hand2",
            )
            tarjeta.grid(
                row=i // columnas,
                column=i % columnas,
                sticky="nsew",
                padx=10,
                pady=10,
            )

            cont.grid_columnconfigure(i % columnas, weight=1)
            cont.grid_rowconfigure(i // columnas, weight=1)

            def abrir_documento(event=None, documento=documento):
                main.seleccionar_inventario(documento)

            icono = main.tk.Label(
                tarjeta,
                text="📄",
                bg=main.COLOR_PANEL,
                fg=main.COLOR_AZUL,
                font=("Segoe UI", 24),
                cursor="hand2",
            )
            icono.pack(side="left", padx=(0, 15))

            info = main.tk.Frame(
                tarjeta,
                bg=main.COLOR_PANEL,
            )
            info.pack(
                side="left",
                fill="both",
                expand=True,
            )

            etiqueta_nombre = main.tk.Label(
                info,
                text=nombre,
                bg=main.COLOR_PANEL,
                fg=main.COLOR_TEXTO,
                font=("Segoe UI", 12, "bold"),
                anchor="w",
                justify="left",
                wraplength=420,
                cursor="hand2",
            )
            etiqueta_nombre.pack(
                fill="x",
                anchor="w",
                pady=(0, 4),
            )

            main.ttk.Button(
                info,
                text=f"Abrir: {nombre}",
                command=abrir_documento,
            ).pack(
                fill="x",
                anchor="w",
                pady=(2, 0),
            )

            tarjeta.bind("<Button-1>", abrir_documento)
            icono.bind("<Button-1>", abrir_documento)
            etiqueta_nombre.bind("<Button-1>", abrir_documento)

    main.construir_opciones_documentos = construir_opciones_documentos


_instalar_selector_portable()
