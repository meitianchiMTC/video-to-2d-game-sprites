#!/usr/bin/env python3
"""Package a standard video-to-2d-game-sprites export for Unity 6 or Cocos 3.8."""
import argparse
import json
from pathlib import Path
import re
import shutil
import zipfile
from PIL import Image


def export(pack, target, output, name):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name):
        raise ValueError('--name must be an ASCII identifier starting with a letter')
    manifest = json.loads((pack / 'manifest.json').read_text(encoding='utf-8-sig'))
    moves = manifest['animations']
    if not moves or len({m['name'] for m in moves}) != len(moves):
        raise ValueError('Need unique animations')
    if not (0 <= manifest['pivotX'] <= 1 and 0 <= manifest['pivotY'] <= 1):
        raise ValueError('Manifest pivot must use bottom-left normalized coordinates')
    if float(manifest.get('pixelsPerUnit', 100)) <= 0:
        raise ValueError('pixelsPerUnit must be positive')
    # Validate all input references before creating the package.
    sources = {}
    for move in moves:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', move['name']):
            raise ValueError('Unsafe animation name')
        if not move['files'] or len(move['files']) != len(move['durationMs']):
            raise ValueError('Frame/duration count mismatch')
        for file, duration in zip(move['files'], move['durationMs']):
            path = (pack / file).resolve()
            if not path.is_relative_to(pack) or not file.startswith('frames/'):
                raise ValueError('Frame must stay inside pack/frames')
            if not isinstance(duration, (int, float)) or not 0 < duration < float('inf'):
                raise ValueError('Frame durations must be positive and finite')
            with Image.open(path) as image:
                if image.mode != 'RGBA' or image.size != (manifest['width'], manifest['height']):
                    raise ValueError(f'Unexpected frame size/mode: {file}')
            sources[file] = path
    zip_path = output.parent / (output.name + '.zip')
    if output.exists() and any(output.iterdir()) or zip_path.exists():
        raise ValueError('Choose a fresh output directory and ZIP path')
    assets = Path(__file__).resolve().parents[1] / 'assets'
    manifest = dict(manifest, defaultAnimation=manifest.get('defaultAnimation', moves[0]['name']))
    if manifest['defaultAnimation'] not in {m['name'] for m in moves}:
        raise ValueError('Default animation missing')
    root = output / 'Assets' / name if target == 'unity6' else output / 'assets' / 'resources' / 'VideoSprites' / name
    root.mkdir(parents=True, exist_ok=True)
    for file, source in sources.items():
        dest = root / file
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    if target == 'unity6':
        script_path = root / 'Editor' / 'ImportVideoSprites.cs'
        template = assets / 'ImportVideoSprites.cs.txt'
        manifest_path = root / 'VideoSpritesManifest.json'
        usage = f'''# {name} — Unity 6 / 6000.x

1. Copy Assets/{name} into the Unity project.
2. Wait for compilation, then choose Tools > Video Sprites > Build {name}.
3. Drag Assets/{name}/Generated/{name}.prefab into the scene.
4. Use Animator.Play("actionName") to switch. A nonloop move returns to the default move when the default loops.

The editor generates .anim clips, an Animator Controller and a Prefab. No manual slicing is needed.
Frames share a fixed canvas, normalized pivot and explicit durations. PPU defaults to 100; edit VideoSpritesManifest.json to change it.
Generated output is managed by the importer; rebuilding updates its Prefab and owned states/transitions. Keep hand edits in copies.
This package uses separate frame textures; atlas/streaming/platform compression are not included.
No project-specific material, collisions or movement code are supplied.
'''
    else:
        script_path = output / 'assets' / 'scripts' / f'{name}VideoSpritePlayer.ts'
        template = assets / 'VideoSpritePlayer.ts.txt'
        manifest_path = root / 'manifest.json'
        usage = f'''# {name} — Cocos Creator 3.8.x

1. Merge assets into your Cocos project, keeping resources/VideoSprites/{name} intact.
2. Add {name}VideoSpritePlayer to a Sprite node under Canvas, then preview.
3. Listen for video-sprite-ready, then call component.play("actionName").
4. initialAction selects a start action; autoPlay and returnToDefault are Inspector options.
   video-sprite-finished emits the completed action name. pause()/resume() control playback.

The component loads PNG ImageAssets, creates full-size SpriteFrames and native AnimationClips at runtime,
preserving per-frame durations and a fixed pivot. No manual PNG import-type change is required.
It does not create editable .anim files or Prefabs in the asset panel.
All actions are preloaded as individual textures; atlas/streaming/platform compression are not included.
'''
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(template.read_text(encoding='utf-8').replace('__PACK_ID__', name), encoding='utf-8')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    memory = len(sources) * manifest['width'] * manifest['height'] * 4 / 1024**2
    usage += f'\nUncompressed frame pixels: approximately {memory:.1f} MiB, plus runtime overhead.\n'
    usage += '\nValidation: frame references, dimensions, RGBA and durations were checked. Editor import/runtime testing has not been performed by this exporter.\n'
    (output / 'README.md').write_text(usage, encoding='utf-8')
    report = {'target': target, 'frameCount': len(sources), 'dataChecksPassed': True,
              'editorRuntimeVerified': False, 'typeCheckPerformed': False}
    (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(output))
    print(json.dumps(report, indent=2))
    print(zip_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', required=True, type=Path)
    parser.add_argument('--target', required=True, choices=['unity6', 'cocos3.8'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--name', default='Character')
    args = parser.parse_args()
    export(args.pack.resolve(), args.target, args.output.resolve(), args.name)


if __name__ == '__main__':
    main()
