import { gzipSync } from 'node:zlib'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const distAssetsDir = new URL('../dist/assets/', import.meta.url)
const distIndex = new URL('../dist/index.html', import.meta.url)
const maxEntryGzipBytes = 500 * 1024

const jsFiles = readdirSync(distAssetsDir)
  .filter(file => file.endsWith('.js'))
  .map(file => {
    const path = join(distAssetsDir.pathname, file)
    return {
      file,
      path,
      size: statSync(path).size,
    }
  })
  .sort((a, b) => b.size - a.size)

if (jsFiles.length === 0) {
  throw new Error('No JavaScript assets found in dist/assets. Run npm run build-only first.')
}

const entry = jsFiles.find(asset => asset.file.startsWith('index-')) ?? jsFiles[0]
const source = readFileSync(entry.path)
const gzipBytes = gzipSync(source).byteLength

console.log(`entry=${entry.file} raw=${entry.size} gzip=${gzipBytes}`)

if (gzipBytes > maxEntryGzipBytes) {
  throw new Error(
    `Entry bundle gzip size ${gzipBytes} exceeds ${maxEntryGzipBytes} bytes. Split route and vendor chunks.`
  )
}

const html = readFileSync(distIndex, 'utf8')
const eagerPageChunks = ['agGrid', 'echarts']
const eagerChunk = eagerPageChunks.find(chunkName => html.includes(`/assets/${chunkName}-`))

if (eagerChunk) {
  throw new Error(`Entry HTML eagerly preloads ${eagerChunk}. Keep page-level heavy chunks lazy-loaded.`)
}
