from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
import image_assets


def main():
    with TemporaryDirectory() as directory:
        public = Path(directory); source = public/'source.png'
        Image.new('RGB', (1800, 1200), '#659dba').save(source)
        with patch.object(image_assets,'PUBLIC',public):
            cards = image_assets.variants_for(source,[320,640,1200],80)
            editorial = image_assets.variants_for(source,[640,960,1600],84)
            assert [v['width'] for v in cards] == [320,640,1200]
            assert [v['width'] for v in editorial] == [640,960,1600]
            for variant in cards+editorial:
                with Image.open(public/variant['url']) as image:
                    assert image.size == (variant['width'],variant['height'])
                    assert abs(image.width/image.height - 1.5) < .01
                    assert image.format == 'WEBP'
            assert image_assets.variants_for(source,[2000,2400])[-1]['width'] == 1800
            assert len(image_assets.variants_for(source,[2000,2400])) == 1
    print('PASS responsive image dimensions, aspect ratio, WebP encoding and no upscaling')


if __name__ == '__main__':main()
