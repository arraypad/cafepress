import urllib, urllib2, httplib2
from elementtree.ElementTree import XML, Element, SubElement, dump
import pprint
from django.conf import settings
from projects.models import *
import poster

# todo: error handling

class CafepressClient(object):
    def __init__(self):
        self.storeId = settings.CAFEPRESS_STORE_ID
        self.apiKey = settings.CAFEPRESS_API_KEY
        self.apiBase = settings.CAFEPRESS_API_BASE
        self.uploadBase = settings.CAFEPRESS_UPLOAD_BASE
        self.apiVersion = '3'
        self.username = settings.CAFEPRESS_USERNAME
        self.password = settings.CAFEPRESS_PASSWORD
        self.userToken = None
        self.http = httplib2.Http()

    def call(self, action, params = {}, useAppKey = True, useToken = False, method = 'GET', debug=False, hasFiles = False, retries=5):
        url = self.uploadBase if hasFiles else self.apiBase
        url += action + '.cp'
        params['v'] = self.apiVersion

        if useAppKey:
            params['appKey'] = self.apiKey
        if useToken:
            params['userToken'] = self.getUserToken()

        headers = {}
        datagen = ''
        if len(params):
            if method == 'POST':
                if hasFiles:
                    import poster
                    poster.streaminghttp.register_openers()
                    datagen, headers = poster.encode.multipart_encode(params)
                else:
                    datagen = urllib.urlencode(params)
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
            else:
                url += '?' + urllib.urlencode(params)

        request = urllib2.Request(url, datagen, headers)

        try:
          content = urllib2.urlopen(request).read()
        except (urllib2.HTTPError, urllib2.URLError), error:
          #content = error.read()
          #print url
          #pprint.pprint(params)
          #print content
          if retries:
            return self.call(action, params, useAppKey, useToken, method, debug, hasFiles, retries - 1)

          raise

        # todo: check resp error code (if useToken then try another token)
        if debug:
          print content

        return XML(content)

    def getUserToken(self):
        if self.userToken is None:
            content = self.call('authentication.getUserToken', {'email': self.username, 'password': self.password})
            self.userToken = content.text
        return self.userToken

    def uploadImage(self, imagePath):
        params = {'cpFile1': open(imagePath, 'rb'), 'folder': 'Images'}
        content = self.call('image.upload', params, useToken=True, method='POST', hasFiles=True, debug=False)
        designId = content.findtext('value')
        return designId
        
    def createDesign(self, svg, width=None, height=None):
        # todo: look into poster.streaminghttp to stream uploaded svgs directly
        design = '<design'
        if width != None:
            design += ' width="' + str(width) + '" height="' + str(height) + '"'
        design += ' />'
        content = self.call('design.save', params = {'value': '<?xml version="1.0"?>' + design, 'svg': svg}, useToken = True, method = 'POST', debug=False)
        designId = content.attrib['id']
        return designId, content.attrib['mediaUrl']
    
    def createProduct(self, merchandiseId, name, media, perspectiveNames=None, colors=None):
        product = '<?xml version="1.0"?><product name="' + name.replace('"', '&quot;') + '" merchandiseId="' + str(merchandiseId) + '" storeId="' + self.storeId + '">'
        for designId, mediaRegion in media:
            product += '<mediaConfiguration dpi="' + str(mediaRegion.dpi) + '" name="' + mediaRegion.name + '" designId="' + str(designId) + '" />'

        defaultColor = None
        if colors:
          for color, default in colors:
            product += '<color id="' + str(color) + '" default="'
            product += 'true' if default else 'false'
            product += '"/>'

            if default:
              defaultColor = color

        product += '</product>'
        content = self.call('product.save', params = {'value': product}, useToken = True, debug=False, method='POST')

        product = {
            'cafepressId': content.attrib['id'],
            'storeUri': content.attrib['storeUri'],
            'name': name,
            'images': {},
        }

        if perspectiveNames == None:
          perspectiveNames = ['Front']

        for image in content.getiterator('productImage'):
            if image.attrib['imageSize'] == settings.CAFEPRESS_PRODUCT_IMAGE_SIZE and \
                    image.attrib['perspectiveName'] in perspectiveNames and \
                    (defaultColor is None or image.attrib['colorId'] == str(defaultColor)):
                product['images'][image.attrib['perspectiveName']] = image.attrib['productUrl'];

        return product

    def importAllMerchandise(self):
      content = self.call('merchandise.list', params = {}, useToken = True)

      for merchandiseContent in content.getiterator('merchandise'):
        try:
          merchandise = Merchandise.objects.get(cafepressId=merchandiseContent.attrib['id'])
        except Merchandise.DoesNotExist:
          merchandise = Merchandise()
          merchandise.cafepressId = merchandiseContent.attrib['id']
          merchandise.sellPrice = merchandiseContent.attrib['sellPrice'] if merchandiseContent.attrib['sellPrice'] != 'N/A' else 0
          merchandise.save()
        
        self.updateMerchandise(merchandise, merchandiseContent)

    def updateMerchandise(self, merchandise, content=None):
      if content == None:
        content = self.call('merchandise.find', params = {'id': merchandise.cafepressId, 'userId': 1}, useToken = True)

      # base attributes
      merchandise.name = content.attrib['name']
      merchandise.basePrice = content.attrib['basePrice']
      merchandise.wildcardBlankProductUrl = content.attrib['wildcardBlankProductUrl']

      # MediaRegions
      existingRegions = dict([(region.name, region) for region in merchandise.mediaregion_set.all()])
      for newRegion in content.getiterator('mediaRegion'):
        if newRegion.attrib['name'] in existingRegions:
          mediaRegion = existingRegions[newRegion.attrib['name']]
          del existingRegions[newRegion.attrib['name']]
        else:
          mediaRegion = MediaRegion()
          mediaRegion.merchandise = merchandise
          mediaRegion.name = newRegion.attrib['name']
        dpi = int(newRegion.attrib['dpi'])
        mediaRegion.width = float(newRegion.attrib['width']) * dpi
        mediaRegion.height = float(newRegion.attrib['height']) * dpi
        mediaRegion.dpi = newRegion.attrib['dpi']
        mediaRegion.save()
      for id, region in existingRegions:
        region.delete()

      # Colors
      existingColors = dict([(str(color.cafepressId), color) for color in merchandise.color_set.all()])
      for newColor in content.getiterator('color'):
        if newColor.attrib['id'] in existingColors:
          color = existingColors[newColor.attrib['id']]
          del existingColors[newColor.attrib['id']]
        else:
          color = Color()
          color.merchandise = merchandise
          color.cafepressId = newColor.attrib['id']
        color.name = newColor.attrib['name']
        color.isDefault = newColor.attrib['default'] == 'true'
        color.swatchUrl = newColor.attrib['colorSwatchUrl']
        color.save()
      for id, color in existingRegions:
        color.delete()

      # Perspectives
      existingPerspectives = dict([(str(perspective.name), perspective) for perspective in merchandise.perspective_set.all()])
      for newPerspective in content.getiterator('perspective'):
        if newPerspective.attrib['name'] in existingPerspectives:
          perspective = existingPerspectives[newPerspective.attrib['name']]
          del existingPerspectives[newPerspective.attrib['name']]
        else:
          perspective = Perspective()
          perspective.merchandise = merchandise
          perspective.name = newPerspective.attrib['name']
        perspective.label = newPerspective.attrib['label']
        perspective.isEditable = newPerspective.attrib['isEditable'] == 'true'
        perspective.width = newPerspective.attrib['pixelWidth']
        perspective.height = newPerspective.attrib['pixelHeight']
        perspective.save()
      for id, perspective in existingRegions:
        perspective.delete()

      merchandise.save()
      return merchandise

