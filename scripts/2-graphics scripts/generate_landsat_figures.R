#!/usr/bin/env Rscript

# Genera las figuras Landsat utilizadas en el manuscrito:
#   Figure2.png  NDVI (paneles a--b) y EVI (paneles c--d)
#   Figure3.png  LSWI anual (columna NDWI del CSV)
#   Figure4.png  temperatura superficial LST
#
# Se eliminan nieve y píxeles problemáticos, se calculan medianas espaciales
# mensuales y luego promedios por año fenológico julio--junio. Los valores de
# EVI fuera del intervalo [-1, 1] se excluyen antes de toda agregación.

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(lubridate)
  library(ggplot2)
  library(patchwork)
  library(scales)
})

# El script vive en scripts/2-graphics scripts/, dos niveles bajo la raiz del
# proyecto (Analisis/); por eso se sube tres niveles desde la ruta del script
# (archivo -> "2-graphics scripts" -> "scripts" -> raiz) para ubicar data/ y
# figures/ de forma robusta sin importar desde donde se invoque Rscript.
project_root <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) == 1) {
    script_path <- normalizePath(sub("^--file=", "", file_arg))
    return(dirname(dirname(dirname(script_path))))
  }
  wd <- normalizePath(getwd())
  if (basename(dirname(wd)) == "scripts") return(dirname(dirname(wd)))
  if (basename(wd) == "scripts") return(dirname(wd))
  wd
}

root_dir <- project_root()
source(file.path(root_dir, "scripts", "2-graphics scripts", "figure_style.R"))
input_file <- file.path(root_dir, "data", "datos_trapiche_landsat.csv")
output_dir <- file.path(root_dir, "figures")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

excluded_point_ids <- c(
  6088, 6089, 5895, 5517, 4349, 4156, 4350, 24900, 25279, 25278,
  26827, 26826, 26650, 26649, 26965
)

figure_config <- list(
  NDVI = list(display = "NDVI", y_label = "NDVI", accuracy = 0.01),
  EVI  = list(display = "EVI", y_label = "EVI", accuracy = 0.01),
  LSWI = list(display = "LSWI", y_label = "LSWI", accuracy = 0.01),
  LST  = list(display = "LST", y_label = "LST (°C)", accuracy = 0.1)
)

raw_data <- read_csv(input_file, show_col_types = FALSE) %>%
  mutate(
    Point_ID = as.integer(Point_ID),
    Snow = as.numeric(Snow),
    DateR = as.Date(Date),
    across(all_of(names(figure_config)), as.numeric),
    EVI = if_else(between(EVI, -1, 1), EVI, NA_real_)
  ) %>%
  filter(
    !is.na(DateR), !is.na(tratamiento), !is.na(Snow),
    Snow != 1, !Point_ID %in% excluded_point_ids
  ) %>%
  mutate(Month = floor_date(DateR, unit = "month"))

base_theme <- manuscript_theme() +
  theme(panel.grid.major.y = element_line(color = "grey85", linewidth = 0.35))

# Fracción del rango de y (desde el máximo) a la que se ancla el borde
# superior de las etiquetas de las líneas verticales. Es la misma en todos
# los paneles y figuras, así las dos etiquetas quedan siempre a la misma
# altura entre sí y entre paneles.
LABEL_TOP_FRACTION <- 0.06

prepare_annual_data <- function(source_column) {
  monthly <- raw_data %>%
    filter(!is.na(.data[[source_column]])) %>%
    group_by(Month, tratamiento) %>%
    summarise(value = median(.data[[source_column]], na.rm = TRUE), .groups = "drop")

  annual <- monthly %>%
    mutate(HydroYear = year(Month) + if_else(month(Month) >= 7, 1L, 0L)) %>%
    filter(HydroYear <= 2026) %>%
    group_by(tratamiento, HydroYear) %>%
    summarise(value = mean(value, na.rm = TRUE), .groups = "drop") %>%
    mutate(tratamiento = standardize_treatment(tratamiento)) %>%
    arrange(HydroYear, tratamiento)

  controls_average <- annual %>%
    filter(tratamiento %in% c("Control 1", "Control 2")) %>%
    group_by(HydroYear) %>%
    summarise(value = mean(value, na.rm = TRUE), .groups = "drop") %>%
    mutate(serie = "Control")

  restored <- annual %>%
    filter(tratamiento == "Restaurado") %>%
    transmute(HydroYear, value, serie = "Restaurado")

  list(annual = annual, smoothed = bind_rows(controls_average, restored))
}

make_annual_panels <- function(source_column, config, label_every = 5) {
  plot_data <- prepare_annual_data(source_column)
  annual <- plot_data$annual
  smoothed_data <- plot_data$smoothed
  year_breaks <- seq(min(annual$HydroYear), max(annual$HydroYear), by = 1)
  year_labels <- ifelse(
    (year_breaks - min(year_breaks)) %% label_every == 0,
    year_breaks, ""
  )
  y_range <- range(annual$value, na.rm = TRUE)
  y_span <- diff(y_range)

  y_padding_top <- 0.15 * y_span
  y_padding_bottom <- 0.05 * y_span
  y_limits <- c(y_range[1] - y_padding_bottom, y_range[2] + y_padding_top)
  label_y <- y_range[2] + 0.06 * y_span

  ref_labels <- tibble(
    x = c(1995, 2020),
    y = label_y,
    label = c("construcción de la represa", "restauración"),
    color = c("#C62828", "#2E7D32")
  )

  common_layers <- list(
    geom_vline(xintercept = 1995, color = "#C62828", linetype = "dashed", linewidth = 1.05),
    geom_vline(xintercept = 2020, color = "#2E7D32", linetype = "longdash", linewidth = 1.0),
    geom_label(
      data = ref_labels,
      aes(x = x, y = y, label = label),
      color = ref_labels$color,
      fill = alpha("white", 0.90),
      linewidth = 0,
      label.padding = unit(0.18, "lines"),
      size = 5, family = "serif", fontface = "plain",
      inherit.aes = FALSE
    ),
    scale_x_continuous(breaks = year_breaks, labels = year_labels),
    scale_y_continuous(limits = y_limits, labels = label_number(accuracy = config$accuracy)),
    labs(x = "Año", y = paste("Valor anual medio de", config$y_label)),
    base_theme
  )

  observed <- ggplot(
    annual, aes(HydroYear, value, color = tratamiento, group = tratamiento)
  ) +
    geom_line(linewidth = 0.9, alpha = 0.92) +
    geom_point(size = 1.8, alpha = 0.92) +
    scale_color_manual(values = TREATMENT_COLORS, drop = FALSE) +
    # Con 4 tratamientos, una sola fila no entra en el ancho del panel y el
    # texto queda cortado (p. ej. "Restau..."); dos filas evitan ese recorte.
    guides(color = guide_legend(nrow = 2, byrow = TRUE)) +
    labs(title = paste(config$display, "anual por tratamiento"), color = "Tratamiento") +
    common_layers

  smoothed <- ggplot(
    smoothed_data, aes(HydroYear, value, color = serie, group = serie)
  ) +
    geom_point(size = 1.8, alpha = 0.42) +
    geom_smooth(
      method = "loess", formula = y ~ x, se = FALSE,
      linewidth = 1.2, span = 0.25
    ) +
    scale_color_manual(values = c(
      "Control" = TREATMENT_COLORS[["Control 1"]],
      "Restaurado" = TREATMENT_COLORS[["Restaurado"]]
    )) +
    guides(color = guide_legend(nrow = 1, byrow = TRUE)) +
    labs(title = paste(config$display, "anual suavizado por tratamiento"), color = "Tratamiento") +
    common_layers

  list(observed = observed, smoothed = smoothed)
}

# Figura 2: NDVI arriba y EVI abajo.
ndvi_panels <- make_annual_panels("NDVI", figure_config$NDVI, label_every = 5)
evi_panels <- make_annual_panels("EVI", figure_config$EVI, label_every = 5)

# En la fila superior (NDVI) se quitan tanto el título del eje x como los
# números de las marcas, porque de lo contrario quedan pegados justo encima
# de los títulos de la fila inferior (EVI) y se solapan con ellos.
no_x_axis <- theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
ndvi_panels$observed <- ndvi_panels$observed + labs(x = NULL) + no_x_axis
ndvi_panels$smoothed <- ndvi_panels$smoothed + labs(x = NULL, y = NULL) + no_x_axis
evi_panels$smoothed <- evi_panels$smoothed + labs(y = NULL)

figure2 <- ((ndvi_panels$observed + ndvi_panels$smoothed) /
  (evi_panels$observed + evi_panels$smoothed)) +
  plot_annotation(tag_levels = "a", tag_suffix = ")") &
  theme(plot.tag = element_text(size = 18, face = "bold", family = "serif"))

ggsave(file.path(output_dir, "Figure2.png"), figure2,
  width = 13.5, height = 10.2, dpi = 320, bg = "white"
)
message("Creada: ", file.path(output_dir, "Figure2.png"))

# Figuras 3 y 4: paneles horizontales (a y b uno al lado del otro).
for (item in list(
  list(source = "LSWI", config = figure_config$LSWI, file = "Figure3.png"),
  list(source = "LST", config = figure_config$LST, file = "Figure4.png")
)) {
  panels <- make_annual_panels(item$source, item$config)
  panels$smoothed <- panels$smoothed + labs(y = NULL)
  combined <- (panels$observed + panels$smoothed) +
    plot_annotation(tag_levels = "a", tag_suffix = ")") &
    theme(plot.tag = element_text(size = 18, face = "bold", family = "serif"))
  output_file <- file.path(output_dir, item$file)
  ggsave(output_file, combined,
    width = 13.5, height = 5.8,
    dpi = 320, bg = "white"
  )
  message("Creada: ", output_file)
}
