#!/usr/bin/env Rscript

# Genera la figura en paneles con las fotografías del proceso de restauración:
#   a) Pozos para plantado
#   b) Restauración 2022
#   c) Restauración consolidada (diciembre 2023)
#   d) Restauración consolidada (diciembre 2025)

suppressPackageStartupMessages({
  library(jpeg)
  library(grid)
  library(ggplot2)
  library(patchwork)
})

# El script vive en scripts/2-graphics scripts/, dos niveles bajo la raiz del
# proyecto (Analisis/); por eso se sube tres niveles desde la ruta del script
# (archivo -> "2-graphics scripts" -> "scripts" -> raiz) para ubicar figures/
# de forma robusta sin importar desde donde se invoque Rscript.
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

# NOTA: la carpeta "anexosfiguras" con las fotografias originales (POZOS PARA
# PLANTADO.JPG, RESTAURACION 2022.JPG, etc.) no forma parte de este
# repositorio (Figure_Restauracion_Paneles.png / FigureS3.png ya estan
# generadas en figures/). Para volver a correr este script hay que crear
# root_dir/anexosfiguras y copiar alli las 4 fotos originales.
anexos_dir <- file.path(root_dir, "anexosfiguras")
output_dir <- file.path(root_dir, "figures")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

# Definición de las fotos y sus títulos
photos_config <- list(
  list(
    file = file.path(anexos_dir, "POZOS PARA PLANTADO.JPG"),
    title = "Pozos para plantado"
  ),
  list(
    file = file.path(anexos_dir, "RESTAURACION 2022.JPG"),
    title = "Restauración 2022"
  ),
  list(
    file = file.path(anexos_dir, "RESTAURACION CONSOLIDADA DICIEMBRE 2023.JPG"),
    title = "Restauración consolidada (diciembre 2023)"
  ),
  list(
    file = file.path(anexos_dir, "RESTAURACION CONSOLODADA DICIEMBRE 2025.JPG"),
    title = "Restauración consolidada (diciembre 2025)"
  )
)

create_photo_panel <- function(photo_info) {
  img <- readJPEG(photo_info$file, native = TRUE)
  img_h <- nrow(img)
  img_w <- ncol(img)

  ggplot() +
    annotation_raster(img, xmin = 0, xmax = img_w, ymin = 0, ymax = img_h, interpolate = TRUE) +
    coord_fixed(ratio = 1, xlim = c(0, img_w), ylim = c(0, img_h), expand = FALSE) +
    labs(title = photo_info$title) +
    theme_void() +
    theme(
      plot.title = element_text(
        family = "serif",
        face = "bold",
        size = 15,
        hjust = 0.5,
        margin = margin(t = 4, b = 8)
      ),
      plot.margin = margin(t = 6, r = 8, b = 6, l = 8),
      plot.tag = element_text(
        family = "serif",
        face = "bold",
        size = 18
      )
    )
}

panels <- lapply(photos_config, create_photo_panel)

fig_restauracion <- (panels[[1]] + panels[[2]]) /
                    (panels[[3]] + panels[[4]]) +
  plot_annotation(tag_levels = "a", tag_suffix = ")") &
  theme(
    plot.tag = element_text(
      size = 18,
      face = "bold",
      family = "serif"
    )
  )

# Guardar en Figures/ con nombres estándar
output_file_main <- file.path(output_dir, "Figure_Restauracion_Paneles.png")
output_file_s3 <- file.path(output_dir, "FigureS3.png")

ggsave(output_file_main, fig_restauracion, width = 13.5, height = 10.5, dpi = 320, bg = "white")
ggsave(output_file_s3, fig_restauracion, width = 13.5, height = 10.5, dpi = 320, bg = "white")

message("Creada: ", output_file_main)
message("Creada: ", output_file_s3)
