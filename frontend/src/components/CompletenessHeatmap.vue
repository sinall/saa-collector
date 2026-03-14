<template>
  <div class="heatmap-container">
    <div class="heatmap-header">
      <span class="title">数据完整度热力图</span>
      <el-select v-model="selectedFrequency" placeholder="选择频度" style="width: 100px" @change="onFrequencyChange">
        <el-option label="日度" value="daily" />
        <el-option label="周度" value="weekly" />
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
import { fetchCompletenessHeatmap, type HeatmapResponse } from '@/utils/api'

const chartRef = ref<HTMLElement>()
const selectedFrequency = ref('monthly')
const loading = ref(false)
const heatmapData = ref<HeatmapResponse | null>(null)
const allPeriods = ref<string[]>([])
const sliderRange = ref<[number, number]>([0, 0])
let chartInstance: echarts.ECharts | null = null

const sliderMarks = computed<Record<number, string>>(() => {
  const marks: Record<number, string> = {}
  const total = allPeriods.value.length
  if (total === 0) return marks

  if (selectedFrequency.value === 'yearly') {
    const step = 3
    for (let i = 0; i < total; i += step) {
      const period = allPeriods.value[i]
      if (period) marks[i] = period
    }
  } else {
    const yearPattern = selectedFrequency.value === 'monthly' 
      ? /^(\d{4})-01$/
      : selectedFrequency.value === 'quarterly'
        ? /^(\d{4})-Q1$/
        : /^(\d{4})-W01$/
    
    allPeriods.value.forEach((period, index) => {
      const match = period.match(yearPattern)
      if (match) {
        marks[index] = match[1] ?? ''
      }
    })
  }

  return marks
})

const formatSliderTooltip = (value: number): string => {
  return allPeriods.value[value] ?? ''
}

const loadHeatmapData = async () => {
  loading.value = true
  try {
    const response = await fetchCompletenessHeatmap(selectedFrequency.value)
    if (response.success && response.data) {
      heatmapData.value = response.data
      allPeriods.value = response.data.periods
      
      if (selectedFrequency.value === 'monthly') {
        const threeYearsAgo = new Date()
        threeYearsAgo.setFullYear(threeYearsAgo.getFullYear() - 3)
        const startIndex = response.data.periods.findIndex((period) => {
          const periodDate = parsePeriodToDate(period, 'monthly')
          return periodDate >= threeYearsAgo
        })
        sliderRange.value = [Math.max(0, startIndex), response.data.periods.length - 1]
      } else {
        sliderRange.value = [0, response.data.periods.length - 1]
      }
      
      renderChart()
    }
  } catch (error) {
    console.error('Failed to load heatmap data:', error)
  } finally {
    loading.value = false
  }
}

const parsePeriodToDate = (period: string, frequency: string): Date => {
  if (frequency === 'daily') {
    return new Date(period)
  } else if (frequency === 'weekly') {
    const [year, week] = period.split('-W')
    const weekNum = parseInt(week, 10)
    const date = new Date(parseInt(year, 10), 0, 1 + (weekNum - 1) * 7)
    return date
  } else if (frequency === 'monthly') {
    const [year, month] = period.split('-')
    return new Date(parseInt(year, 10), parseInt(month, 10) - 1, 1)
  } else if (frequency === 'quarterly') {
    const [year, quarter] = period.split('-Q')
    const quarterNum = parseInt(quarter, 10)
    return new Date(parseInt(year, 10), (quarterNum - 1) * 3, 1)
  } else {
    return new Date(parseInt(period, 10), 0, 1)
  }
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

  const chartData: [number, number, number][] = []
  data_types.forEach((dt, yIndex) => {
    const values = matrix[dt.key] || []
    const slicedValues = values.slice(startIdx, endIdx + 1)
    slicedValues.forEach((value, xIndex) => {
      chartData.push([xIndex, yIndex, value])
    })
  })

  const maxValue = Math.max(...chartData.map(d => d[2]))
  const minValue = Math.min(...chartData.map(d => d[2]))

  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const [xIndex, yIndex, value] = params.data
        const period = displayPeriods[xIndex] ?? ''
        const dataType = data_types[yIndex]?.label ?? ''
        return `${period}<br/>${dataType}: ${(value * 100).toFixed(1)}%`
      },
    },
    grid: {
      top: 30,
      bottom: 50,
      left: 120,
      right: 30,
    },
    xAxis: {
      type: 'category',
      data: displayPeriods,
      axisLabel: {
        rotate: 45,
        fontSize: 10,
        showMaxLabel: true,
      },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: data_types.map(dt => dt.label),
      splitArea: { show: false },
    },
    visualMap: {
      min: minValue,
      max: maxValue,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: {
        color: ['#ff4d4f', '#faad14', '#52c41a'],
      },
      text: ['100%', '0%'],
      show: false,
    },
    series: [
      {
        type: 'heatmap',
        data: chartData,
        label: { show: false },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
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

  const gridWidth = chartRef.value.clientWidth - 120 - 30
  const cellWidth = gridWidth / displayPeriods.length
  const halfCell = cellWidth / 2
  const sliderContainer = document.querySelector('.slider-container')
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
  padding: 10px calc(30px + var(--half-cell, 0px)) 30px calc(120px + var(--half-cell, 0px));
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 10px;
}

.time-slider :deep(.el-slider__runway) {
  margin: 0;
}

.time-slider {
  width: 100%;
}

.time-slider :deep(.el-slider__marks-text) {
  font-size: 11px;
  color: #909399;
}
</style>
