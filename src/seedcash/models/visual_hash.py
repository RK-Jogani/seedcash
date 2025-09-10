 
import numpy as np
import hashlib
import colorsys
from PIL import Image, ImageEnhance, ImageFilter

# Función para evolucionar la cuadrícula
def evolve_grid(grid, generations):
    size = grid.shape[0]
    for _ in range(generations):
        neighbors = np.zeros((size, size), dtype=int)
        neighbors[1:, 1:] += grid[:-1, :-1]
        neighbors[1:, :-1] += grid[:-1, 1:]
        neighbors[:-1, 1:] += grid[1:, :-1]
        neighbors[:-1, :-1] += grid[1:, 1:]
        neighbors[:-1, :] += grid[1:, :]
        neighbors[1:, :] += grid[:-1, :]
        neighbors[:, :-1] += grid[:, 1:]
        neighbors[:, 1:] += grid[:, :-1]
        grid = ((neighbors == 3) | ((grid == 1) & (neighbors == 2))).astype(int)
    return grid

# Función para generar una paleta de colores exóticos
def generate_exotic_palette(base_hue, num_colors=4):
    palette = []
    for i in range(num_colors):
        hue = (base_hue + i * 0.38197) % 1  # Razón áurea conjugada
        saturation = 0.7 + np.random.random() * 0.3
        lightness = 0.3 + np.random.random() * 0.4
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        palette.append((int(r*255), int(g*255), int(b*255)))

    # Asegurar contraste ordenando y potencialmente intercambiando colores
    palette.sort(key=lambda x: sum(x))
    if sum(palette[0]) > 382:  # Si el color más oscuro es demasiado claro
        palette[0] = (0, 0, 0)  # Reemplazar con negro
    if sum(palette[-1]) < 382:  # Si el color más claro es demasiado oscuro
        palette[-1] = (255, 255, 255)  # Reemplazar con blanco

    return palette

# Función para generar un color basado en un valor
def generate_color(v, color_palette):
    index = int(v * (len(color_palette) - 1))
    return color_palette[index]

# Función principal para generar el lifehash
def optimized_lifehash(data, size=32, generations=50):
    # Generar hash
    hash_object = hashlib.sha256(data.encode())
    hash_digest = hash_object.digest()

    # Semilla para generar la cuadrícula aleatoria
    np.random.seed(int.from_bytes(hash_digest[:4], byteorder='big'))
    grid = np.random.choice([0, 1], size=(size, size))

    # Evolución de la cuadrícula
    final_grid = evolve_grid(grid, generations)

    # Generar paleta de colores
    base_hue = int.from_bytes(hash_digest[4:6], byteorder='big') / 65535.0
    color_palette = generate_exotic_palette(base_hue)

    # Asignar colores a la cuadrícula final
    colors = np.array([generate_color(v, color_palette) for v in final_grid.flatten()]).reshape(final_grid.shape + (3,))

    # Aplicar simetría
    colors = np.maximum(colors, np.flip(colors, axis=1))
    colors = np.maximum(colors, np.flip(colors, axis=0))

    return colors.astype(np.uint8)

# Función para mejorar el contraste de una imagen
def enhance_contrast(image):
    # Convertir a espacio de color LAB
    lab = image.convert('LAB')
    l, a, b = lab.split()

    # Mejorar el canal L (luminosidad)
    l = ImageEnhance.Contrast(l).enhance(1.5)

    # Unir canales y convertir de nuevo a RGB
    enhanced = Image.merge('LAB', (l, a, b)).convert('RGB')
    return enhanced

# Función final para generar una imagen a partir de un "fingerprint"
def generate_lifehash(fingerprint):
    colors = optimized_lifehash(fingerprint)
    pil_image = Image.fromarray(colors)
    pil_image = pil_image.filter(ImageFilter.GaussianBlur(radius=0.5))
    pil_image = enhance_contrast(pil_image)
    pil_image = pil_image.resize((27, 27), Image.LANCZOS)
    return pil_image