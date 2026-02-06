#!/usr/bin/env python3
"""
Extract frames from animated GIF and convert to bitmaps for Meshtastic firmware
Converts GIF animation frames to 24x24 monochrome bitmaps in PROGMEM format
"""

from PIL import Image
import sys
import os

def extract_gif_frames(gif_path, max_frames=None):
    """
    Extract frames from animated GIF
    
    Args:
        gif_path: Path to GIF file
        max_frames: Maximum number of frames to extract (None = all)
    
    Returns:
        List of PIL Image objects
    """
    if not os.path.exists(gif_path):
        print(f"Error: GIF file not found: {gif_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading GIF: {gif_path}", file=sys.stderr)
    
    img = Image.open(gif_path)
    frames = []
    
    try:
        frame_count = 0
        while True:
            # Copy current frame
            frame = img.copy()
            frames.append(frame)
            frame_count += 1
            
            if max_frames and frame_count >= max_frames:
                break
            
            # Move to next frame
            img.seek(img.tell() + 1)
    except EOFError:
        pass  # End of GIF animation
    
    print(f"Extracted {len(frames)} frames from GIF", file=sys.stderr)
    return frames

def frame_to_bitmap(frame, size=24, threshold=128, dither=False):
    """
    Convert image frame to monochrome bitmap
    
    Args:
        frame: PIL Image object
        size: Output size in pixels (default 24x24)
        threshold: Grayscale threshold for black/white (0-255)
        dither: Use Floyd-Steinberg dithering instead of threshold
    
    Returns:
        List of bytes for PROGMEM array
    """
    # Convert to RGBA to handle transparency
    if frame.mode == 'P':
        frame = frame.convert('RGBA')
    elif frame.mode != 'RGBA':
        frame = frame.convert('RGBA')
    
    # Create white background and paste frame (handles transparency)
    background = Image.new('RGBA', frame.size, (255, 255, 255, 255))
    background.paste(frame, (0, 0), frame)
    
    # Convert to grayscale
    img = background.convert('L')
    
    # Resize to target size with high-quality resampling
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Convert to monochrome (1-bit)
    if dither:
        # Use Floyd-Steinberg dithering for better grayscale representation
        img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
    else:
        # Simple threshold
        img = img.point(lambda x: 0 if x < threshold else 255, '1')
    
    # Convert to bitmap array (3 bytes per row for 24-bit width)
    pixels = list(img.getdata())
    width = img.width
    height = img.height
    bytes_per_row = (width + 7) // 8
    
    bitmap = []
    for y in range(height):
        row_bytes = [0] * bytes_per_row
        for x in range(width):
            if pixels[y * width + x] == 0:  # Black pixel
                byte_index = x // 8
                bit_index = 7 - (x % 8)
                row_bytes[byte_index] |= (1 << bit_index)
        bitmap.extend(row_bytes)
    
    return bitmap

def format_progmem(bitmap, var_name, width, height):
    """Format bitmap as PROGMEM C++ array"""
    bytes_per_row = (width + 7) // 8
    output = f"const uint8_t {var_name}[] PROGMEM = {{\n"
    
    for row in range(height):
        row_start = row * bytes_per_row
        row_bytes = bitmap[row_start:row_start + bytes_per_row]
        
        hex_values = ', '.join(f'0x{b:02x}' for b in row_bytes)
        
        # Visual comment
        visual = ''
        for byte_val in row_bytes:
            for bit in range(7, -1, -1):
                visual += '▓' if (byte_val & (1 << bit)) else '░'
        
        # Add row markers
        if row == 0:
            comment = f" // {visual} (top)"
        elif row == height - 1:
            comment = f" // {visual} (bottom)"
        else:
            comment = f" // {visual}"
        
        output += f"    {hex_values}, {comment}\n"
    
    output += "};"
    return output

def show_preview(bitmap, width, height):
    """Show ASCII preview of bitmap"""
    bytes_per_row = (width + 7) // 8
    for row in range(height):
        row_start = row * bytes_per_row
        row_bytes = bitmap[row_start:row_start + bytes_per_row]
        line = ''
        for byte_val in row_bytes:
            for bit in range(7, -1, -1):
                line += '██' if (byte_val & (1 << bit)) else '  '
        print(line, file=sys.stderr)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert animated GIF to bitmap animation for Meshtastic')
    parser.add_argument('gif', help='Path to animated GIF file')
    parser.add_argument('--frames', type=int, help='Maximum number of frames to extract')
    parser.add_argument('--size', type=int, default=24, help='Output size in pixels (default: 24)')
    parser.add_argument('--threshold', type=int, default=128, help='Black/white threshold 0-255 (default: 128, ignored with --dither)')
    parser.add_argument('--dither', action='store_true', help='Use Floyd-Steinberg dithering instead of threshold')
    parser.add_argument('--name', default='skull_frame', help='Base variable name (default: skull_frame)')
    parser.add_argument('--output', '-o', default='src/graphics/skull_animation.h', help='Output header file path (default: src/graphics/skull_animation.h)')
    parser.add_argument('--preview', action='store_true', help='Show ASCII preview of each frame')
    
    args = parser.parse_args()
    
    # Extract frames from GIF
    frames = extract_gif_frames(args.gif, args.frames)
    
    if not frames:
        print("Error: No frames extracted", file=sys.stderr)
        sys.exit(1)
    
    conversion_method = "Floyd-Steinberg dithering" if args.dither else f"threshold={args.threshold}"
    print(f"\nGenerating {len(frames)} bitmaps ({conversion_method})...\n", file=sys.stderr)
    
    # Generate header file content
    guard_name = os.path.basename(args.output).upper().replace('.', '_').replace('-', '_')
    
    output_lines = []
    output_lines.append(f"// Auto-generated from {os.path.basename(args.gif)}")
    cmd_args = f"{args.gif}"
    if args.dither:
        cmd_args += " --dither"
    elif args.threshold != 128:
        cmd_args += f" --threshold {args.threshold}"
    output_lines.append(f"// DO NOT EDIT MANUALLY - regenerate with: python bin/gif_to_bitmap.py {cmd_args}")
    output_lines.append(f"#pragma once")
    output_lines.append("")
    output_lines.append(f"// Animation: {len(frames)} frames, {args.size}x{args.size} pixels")
    output_lines.append(f"// Conversion: {conversion_method}")
    output_lines.append(f"#define SKULL_WIDTH {args.size}")
    output_lines.append(f"#define SKULL_HEIGHT {args.size}")
    output_lines.append("")
    
    # Convert each frame to bitmap
    for i, frame in enumerate(frames, 1):
        bitmap = frame_to_bitmap(frame, args.size, args.threshold, dither=args.dither)
        
        if args.preview:
            print(f"\nPreview of frame {i}:", file=sys.stderr)
            show_preview(bitmap, args.size, args.size)
            print(file=sys.stderr)
        
        output_lines.append(f"// Frame {i}/{len(frames)}")
        var_name = f"{args.name}{i}"
        output_lines.append(format_progmem(bitmap, var_name, args.size, args.size))
        output_lines.append("")
    
    # Generate array of pointers for easy iteration
    output_lines.append(f"// Array of frame pointers for animation")
    output_lines.append(f"#define SKULL_FRAME_COUNT {len(frames)}")
    output_lines.append(f"const uint8_t* const {args.name}_frames[] PROGMEM = {{")
    for i in range(1, len(frames) + 1):
        comma = ',' if i < len(frames) else ''
        output_lines.append(f"    {args.name}{i}{comma}")
    output_lines.append("};")
    
    # Write to file
    output_path = args.output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(output_lines))
    
    print(f"\n✓ Generated {output_path}", file=sys.stderr)
    print(f"  {len(frames)} frames, {args.size}x{args.size} pixels", file=sys.stderr)
    print(f"\nTo use: #include \"skull_animation.h\" in your images.h", file=sys.stderr)
