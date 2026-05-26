import { ref, computed } from 'vue'
import { fetchDataTypesConfig } from '@/utils/api'

export interface DataTypeConfig {
  key: string
  label: string
  table: string | null
  frequency?: string | null
  stock_level: boolean
  group?: string
  show_completeness: boolean
  need_date: boolean
  stock_column?: string
  supports_integrity_check: boolean
  order: number
}

export interface DataTypeGroup {
  key: string
  label: string
  order: number
}

const dataTypes = ref<DataTypeConfig[]>([])
const groups = ref<DataTypeGroup[]>([])
const loaded = ref(false)
const loading = ref(false)

export function useDataTypes() {
  async function loadDataTypes(forceReload = false): Promise<void> {
    if (loaded.value && !forceReload) return
    if (loading.value) return

    loading.value = true
    try {
      const response = await fetchDataTypesConfig()
      dataTypes.value = response.data_types
      groups.value = response.groups
      loaded.value = true
    } catch (error) {
      console.error('Failed to load data types config:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const groupedDataTypes = computed(() => {
    const result: Record<string, DataTypeConfig[]> = {}
    for (const dt of dataTypes.value) {
      const group = dt.group || 'other'
      if (!result[group]) {
        result[group] = []
      }
      result[group].push(dt)
    }
    return result
  })

  function getLabel(key: string): string {
    return dataTypes.value.find(dt => dt.key === key)?.label || key
  }

  const completenessTypes = computed(() =>
    dataTypes.value.filter(dt => dt.show_completeness)
  )

  const integrityCheckTypes = computed(() =>
    dataTypes.value.filter(dt => dt.supports_integrity_check)
  )

  function getConfig(key: string): DataTypeConfig | undefined {
    return dataTypes.value.find(dt => dt.key === key)
  }

  function getTypesByGroup(groupKey: string): DataTypeConfig[] {
    return dataTypes.value.filter(dt => dt.group === groupKey)
  }

  return {
    dataTypes,
    groups,
    loaded,
    loading,
    groupedDataTypes,
    completenessTypes,
    integrityCheckTypes,
    loadDataTypes,
    getLabel,
    getConfig,
    getTypesByGroup,
  }
}
