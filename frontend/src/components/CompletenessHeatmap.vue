<template>
  <div class="heatmap-container">
    <div class="heatmap-header">
      <span class="title">数据完整度热力图</span>
      <el-select
        v-if="!hideFrequencySelector"
        v-model="selectedFrequency"
        placeholder="选择频度"
        style="width: 100px"
        @change="onFrequencyChange"
      >
        <el-option label="日度" value="daily" />
        <el-option label="月度" value="monthly" />
        <el-option label="季度" value="quarterly" />
        <el-option label="年度" value="yearly" />
      </el-select>
    </div>

    <div v-loading="loading" class="heatmap-chart" ref="chartRef"></div>

    <div class="slider-container" v-if="allPeriods.length > 0">
      <el-slider
        v-model="sliderRange"
        range
        :min="0"
        :max="allPeriods.length - 1"
        :marks="sliderMarks"
        :format-tooltip="formatSliderTooltip"
        @change="onSliderChange"
        class="time-slider"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { fetchCompletenessHeatmap, type HeatmapResponse, type IntegrityReportHeatmapData } from '@/utils/api'

type ExternalHeatmapData = HeatmapResponse | IntegrityReportHeatmapData

interface MergedCell {
  xStart: number
  xSpan: number
  yIndex: number
  value: number
  period: string
  periodRange: string
}

const props = withDefaults(defineProps<{
  externalData?: ExternalHeatmapData | null
  hideFrequencySelector?: boolean
  viewFrequency?: string
}>(), {
  externalData: null,
  hideFrequencySelector: false,
  viewFrequency: ''
})

const chartRef = ref<HTMLElement>()
const selectedFrequency = ref('monthly')
const loading = ref(false)
const heatmapData = ref<HeatmapResponse | null>(null)
const allPeriods = ref<string[]>([])
const sliderRange = ref<[number, number]>([0, 0])
let chartInstance: echarts.ECharts | null = null
let mergedCellsCache: MergedCell[] = []

const effectiveFrequency = computed(() => {
  return props.viewFrequency || selectedFrequency.value
})

const sliderMarks = computed<Record<number, string>>(() => {
  const marks: Record<number, string> = {}
  const total = allPeriods.value.length
  if (total === 0) return marks

  if (effectiveFrequency.value === 'yearly') {
    const step = 5
    for (let i = 0; i < total; i += step) {
      const period = allPeriods.value[i]
      if (period) marks[i] = period
    }
  } else {
    const yearPattern = effectiveFrequency.value === 'monthly'
      ? /^(\d{4})-01$/
      : effectiveFrequency.value === 'quarterly'
        ? /^(\d{4})-Q1$/
        : /^(\d{4})-W01$/

    let yearCount = 0
    allPeriods.value.forEach((period, index) => {
      const match = period.match(yearPattern)
      if (match) {
        yearCount++
        if (yearCount % 2 === 1) {
          marks[index] = match[1] ?? ''
        }
      }
    })
  }

  return marks
})

const formatSliderTooltip = (value: number): string => {
  return allPeriods.value[value] ?? ''
}

const DEFAULT_DISPLAY_START_YEAR = 2009

const initFromData = async (data: ExternalHeatmapData, frequency: string) => {
  heatmapData.value = data as HeatmapResponse
  allPeriods.value = data.periods

  const targetPeriod = frequency === 'monthly'
    ? `${DEFAULT_DISPLAY_START_YEAR}-01`
    : frequency === 'quarterly'
      ? `${DEFAULT_DISPLAY_START_YEAR}-Q1`
      : frequency === 'yearly'
        ? `${DEFAULT_DISPLAY_START_YEAR}`
        : null

  const targetIndex = targetPeriod
    ? allPeriods.value.findIndex(p => p === targetPeriod)
    : -1
  const endIndex = allPeriods.value.length - 1

  sliderRange.value = targetIndex !== -1
    ? [targetIndex, endIndex]
    : [0, allPeriods.value.length - 1]

  await nextTick()
  renderChart()
  setTimeout(() => {
    chartInstance?.resize()
    updateSliderAlignment()
  }, 100)
}

const loadHeatmapData = async () => {
  if (props.externalData) {
    initFromData(props.externalData, props.viewFrequency || selectedFrequency.value)
    return
  }

  if (props.hideFrequencySelector) {
    return
  }

  loading.value = true
  try {
    const response = await fetchCompletenessHeatmap(selectedFrequency.value)
    if (response.success && response.data) {
      initFromData(response.data, selectedFrequency.value)
    }
  } catch (error) {
    console.error('Failed to load heatmap data:', error)
  } finally {
    loading.value = false
  }
}

const getColorByValue = (value: number): string => {
  if (value === -1) return '#f5f5f5'
  if (value < 0.25) return '#fecaca'
  if (value < 0.5) return '#fed7aa'
  if (value < 0.75) return '#fef08a'
  if (value < 0.9) return '#bbf7d0'
  return '#86efac'
}

const getPeriodLabel = (periodIndex: number, dataFrequency: string | undefined | null, periods: string[], viewFrequency?: string): string => {
  const period = periods[periodIndex]
  if (!period) return ''

  if (dataFrequency === 'quarterly' && viewFrequency === 'monthly') {
    const match = period.match(/^(\d{4})-(\d{2})$/)
    if (match && match[1] && match[2]) {
      const year = match[1]
      const month = parseInt(match[2])
      const quarter = Math.ceil(month / 3)
      return `${year}-Q${quarter}`
    }
  } else if (dataFrequency === 'yearly') {
    if (viewFrequency === 'monthly') {
      return period.substring(0, 4)
    } else if (viewFrequency === 'quarterly') {
      const match = period.match(/^(\d{4})-Q(\d)$/)
      if (match && match[1]) {
        return match[1]
      }
      return period.substring(0, 4)
    }
  }

  return period
}

const getPeriodRange = (periodIndex: number, dataFrequency: string | undefined | null, periods: string[], viewFrequency?: string): string => {
  const period = periods[periodIndex]
  if (!period) return ''

  if (dataFrequency === 'quarterly' && viewFrequency === 'monthly') {
    const match = period.match(/^(\d{4})-(\d{2})$/)
    if (match && match[1] && match[2]) {
      const year = match[1]
      const month = parseInt(match[2])
      const quarter = Math.ceil(month / 3)
      const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月',
                          '7月', '8月', '9月', '10月', '11月', '12月']
      const startMonth = (quarter - 1) * 3
      return `${year}-Q${quarter} (${monthNames[startMonth]}-${monthNames[startMonth + 2]})`
    }
  } else if (dataFrequency === 'yearly') {
    if (viewFrequency === 'monthly') {
      return period.substring(0, 4)
    } else if (viewFrequency === 'quarterly') {
      const match = period.match(/^(\d{4})-Q(\d)$/)
      if (match && match[1]) {
        return match[1]
      }
      return period.substring(0, 4)
    }
  }

  return period
}

const prepareMergedCells = (
  dataTypes: { key: string; label: string; frequency?: string | null }[],
  matrix: Record<string, number[]>,
  startIdx: number,
  endIdx: number,
  viewFrequency: string,
  displayPeriods: string[]
): MergedCell[] => {
  const cells: MergedCell[] = []

  dataTypes.forEach((dt, yIndex) => {
    const values = matrix[dt.key] || []
    const slicedValues = values.slice(startIdx, endIdx + 1)
    const dataFreq = dt.frequency

    if (dataFreq === null || dataFreq === undefined) {
      slicedValues.forEach((value, xIndex) => {
        cells.push({
          xStart: xIndex,
          xSpan: 1,
          yIndex,
          value,
          period: displayPeriods[xIndex] ?? '',
          periodRange: displayPeriods[xIndex] ?? ''
        })
      })
      return
    }

    let shouldMerge = false
    let span = 1

    if (viewFrequency === 'monthly' && dataFreq === 'quarterly') {
      shouldMerge = true
      span = 3
    } else if (viewFrequency === 'monthly' && dataFreq === 'yearly') {
      shouldMerge = true
      span = 12
    } else if (viewFrequency === 'quarterly' && dataFreq === 'yearly') {
      shouldMerge = true
      span = 4
    }

    if (shouldMerge) {
      for (let i = 0; i < slicedValues.length; i += span) {
        const value = slicedValues[i] ?? 0
        cells.push({
          xStart: i,
          xSpan: Math.min(span, slicedValues.length - i),
          yIndex,
          value,
          period: getPeriodLabel(i, dataFreq, displayPeriods, viewFrequency),
          periodRange: getPeriodRange(i, dataFreq, displayPeriods, viewFrequency)
        })
      }
    } else {
      slicedValues.forEach((value, xIndex) => {
        cells.push({
          xStart: xIndex,
          xSpan: 1,
          yIndex,
          value,
          period: displayPeriods[xIndex] ?? '',
          periodRange: displayPeriods[xIndex] ?? ''
        })
      })
    }
  })

  return cells
}

const getCompletenessColor = (completeness: number): string => {
  if (completeness < 0.5) return '#f56c6c'
  if (completeness < 0.75) return '#e6a23c'
  if (completeness < 0.9) return '#409eff'
  return '#67c23a'
}

const calculateRowCompleteness = (yIndex: number): number => {
  const rowCells = mergedCellsCache.filter(cell => cell.yIndex === yIndex && cell.value !== -1)
  if (rowCells.length === 0) return -1
  const sum = rowCells.reduce((acc, cell) => acc + cell.value, 0)
  return sum / rowCells.length
}

const renderChart = () => {
  if (!chartRef.value || !heatmapData.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const { data_types, matrix } = heatmapData.value
  const [startIdx, endIdx] = sliderRange.value
  const displayPeriods = allPeriods.value.slice(startIdx, endIdx + 1)

  if (displayPeriods.length === 0) {
    chartInstance.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'center',
      },
    }, true)
    return
  }

  mergedCellsCache = prepareMergedCells(
    data_types,
    matrix,
    startIdx,
    endIdx,
    effectiveFrequency.value,
    displayPeriods
  )

  const rowCompleteness = data_types.map((_, idx) => calculateRowCompleteness(idx))

  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const cell = mergedCellsCache[params.dataIndex]
        if (!cell) return ''
        const dataType = data_types[cell.yIndex]?.label ?? ''
        if (cell.value === -1) {
          return cell.periodRange ? `${cell.periodRange}<br/>${dataType}: 不适用` : `${dataType}: 不适用`
        }
        const valueText = `${dataType}: ${(cell.value * 100).toFixed(1)}%`
        return cell.periodRange ? `${cell.periodRange}<br/>${valueText}` : valueText
      },
    },
    grid: {
      top: 30,
      bottom: 50,
      left: 120,
      right: 70,
    },
    xAxis: {
      type: 'category',
      data: displayPeriods,
      boundaryGap: true,
      position: 'bottom',
      offset: 20,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        rotate: 45,
        fontSize: 10,
        showMaxLabel: true,
        align: 'center',
        margin: 8,
      },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: data_types.map(dt => dt.label),
      boundaryGap: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitArea: { show: false },
    },
    series: [
      {
        type: 'custom',
        renderItem: (params: any, api: any) => {
          const cell = mergedCellsCache[params.dataIndex]
          if (!cell) return { type: 'rect', shape: { x: 0, y: 0, width: 0, height: 0 } }

          const coord0 = api.coord([0, 0])
          const coord1 = api.coord([1, 1])

          const singleWidth = coord1[0] - coord0[0]

          const gridSize = api.size([1, 1])
          const singleHeight = gridSize ? Math.abs(gridSize[1]) : 30

          const startX = coord0[0] + singleWidth * cell.xStart - singleWidth / 2
          const startY = coord0[1] - singleHeight * cell.yIndex - singleHeight / 2

          return {
            type: 'rect',
            shape: {
              x: startX,
              y: startY,
              width: singleWidth * cell.xSpan,
              height: singleHeight
            },
            style: api.style({
              fill: getColorByValue(cell.value),
              stroke: '#fff',
              lineWidth: 1
            }),
            emphasis: {
              style: {
                stroke: '#333',
                lineWidth: 2,
                shadowBlur: 10,
                shadowColor: 'rgba(0, 0, 0, 0.5)'
              }
            }
          }
        },
        data: mergedCellsCache.map((cell, idx) => ({
          value: cell.value,
          dataIndex: idx
        })),
      },
      {
        type: 'custom',
        renderItem: (params: any, api: any) => {
          const yIndex = params.dataIndex
          const completeness = rowCompleteness[yIndex] ?? -1
          if (completeness === -1) return { type: 'group', children: [] }

          const coord0 = api.coord([0, 0])
          const coord1 = api.coord([1, 1])
          const singleHeight = Math.abs(coord1[1] - coord0[1])
          const centerY = coord0[1] - singleHeight * yIndex

          const chartWidth = chartRef.value?.clientWidth ?? 600
          const textX = chartWidth - 55

          return {
            type: 'group',
            children: [
              {
                type: 'rect',
                shape: {
                  x: textX - 2,
                  y: centerY - singleHeight * 0.35,
                  width: 44,
                  height: singleHeight * 0.7
                },
                style: {
                  fill: '#f5f7fa',
                  borderRadius: 3
                }
              },
              {
                type: 'text',
                style: {
                  x: textX + 20,
                  y: centerY,
                  text: `${Math.round(completeness * 100)}%`,
                  fill: getCompletenessColor(completeness),
                  font: 'bold 12px sans-serif',
                  textAlign: 'center',
                  textVerticalAlign: 'middle'
                }
              }
            ]
          }
        },
        data: data_types.map((_, idx) => ({ value: rowCompleteness[idx], dataIndex: idx })),
        silent: true
      }
    ],
  }

  chartInstance.setOption(option, true)
  setTimeout(updateSliderAlignment, 50)
}

const onFrequencyChange = () => {
  loadHeatmapData()
}

const onSliderChange = () => {
  renderChart()
}

const handleResize = () => {
  chartInstance?.resize()
  updateSliderAlignment()
}

const updateSliderAlignment = () => {
  if (!chartRef.value || !heatmapData.value) return
  const [startIdx, endIdx] = sliderRange.value
  const displayPeriods = allPeriods.value.slice(startIdx, endIdx + 1)
  if (displayPeriods.length === 0) return

  const gridWidth = chartRef.value.clientWidth - 120 - 70
  const cellWidth = gridWidth / displayPeriods.length
  const halfCell = cellWidth / 2
  const sliderContainer = document.querySelector('.slider-container') as HTMLElement | null
  if (sliderContainer) {
    sliderContainer.style.setProperty('--half-cell', `${halfCell}px`)
  }
}

onMounted(() => {
  loadHeatmapData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})

watch(heatmapData, () => {
  renderChart()
})

watch(() => props.externalData, (newData) => {
  if (newData) {
    initFromData(newData, props.viewFrequency || selectedFrequency.value)
  }
})

watch(() => props.viewFrequency, (newFreq) => {
  if (props.externalData && newFreq) {
    initFromData(props.externalData, newFreq)
  }
})
</script>

<style scoped>
.heatmap-container {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
}

.heatmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.heatmap-header .title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.heatmap-chart {
  width: 100%;
  height: 380px;
}

.slider-container {
  padding: 5px calc(70px + var(--half-cell, 0px)) 10px calc(120px + var(--half-cell, 0px));
  margin-top: 0;
}

.time-slider {
  width: 100%;
}

.time-slider :deep(.el-slider__runway) {
  margin: 0;
  background-color: #dcdfe6;
}

.time-slider :deep(.el-slider__bar) {
  background-color: #909399;
}

.time-slider :deep(.el-slider__button) {
  width: 8px;
  height: 20px;
  border-radius: 0;
  border: none;
  background: #c0c4cc;
}

.time-slider :deep(.el-slider__marks-text) {
  font-size: 11px;
  color: #909399;
}
</style>
