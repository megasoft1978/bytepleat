import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]

class WindowsAdapterManifestTests(unittest.TestCase):
    def test_manifest_clsids_and_namespaces(self):
        root = ET.parse(ROOT / 'package' / 'AppxManifest.xml').getroot()
        ns = {
            'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
            'uap5': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/5',
            'uap10': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
            'd4': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/4',
            'd5': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/5',
            'com': 'http://schemas.microsoft.com/appx/manifest/com/windows10',
        }
        classes = {x.attrib['Id'].upper() for x in root.findall('.//com:Class', ns)}
        verbs = root.findall('.//d5:Verb', ns)
        self.assertTrue(verbs)
        self.assertTrue(all(v.attrib['Clsid'].upper() in classes for v in verbs))
        item_types = root.findall('.//d5:ItemType', ns)
        self.assertEqual({x.attrib['Type'] for x in item_types}, {'*', 'Directory'})
        self.assertTrue(all(x.find('d5:Verb', ns) is not None for x in item_types))
        self.assertIsNotNone(root.find('{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Properties/{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Logo'))
        self.assertIsNotNone(root.find('.//uap:VisualElements', ns).attrib.get('Square150x150Logo'))
        self.assertIsNotNone(root.find('.//uap:VisualElements', ns).attrib.get('Square44x44Logo'))
        alias = root.find('.//uap5:ExecutionAlias', ns)
        self.assertEqual(alias.attrib['Alias'], 'bytepleat-desktop.exe')
        app = root.find('.//{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Application')
        self.assertEqual(app.attrib['{http://schemas.microsoft.com/appx/manifest/uap/windows10/10}RuntimeBehavior'], 'packagedClassicApp')

    def test_packaging_has_unsigned_and_signed_paths_without_validation_bypass(self):
        script = (ROOT / 'package' / 'Build-Package.ps1').read_text()
        self.assertIn('Copy-Item', script)
        self.assertIn("'Square150x150Logo.png','Square44x44Logo.png','StoreLogo.png'", script)
        self.assertIn('if ($Sign)', script)
        self.assertIn('& $makeappx pack /d $stage /p $msix /o', script)
        self.assertNotIn('/nv', script)

if __name__ == '__main__':
    unittest.main()
