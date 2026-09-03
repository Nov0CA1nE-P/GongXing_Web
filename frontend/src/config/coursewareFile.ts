export const COURSEWARE_FILE_FORMATS = [
  {
    extension: '.pdf',
    mime: 'application/pdf',
    label: 'PDF',
  },
  {
    extension: '.pptx',
    mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    label: 'PPTX',
  },
  {
    extension: '.docx',
    mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    label: 'DOCX',
  },
  {
    extension: '.jpg',
    mime: 'image/jpeg',
    label: 'JPG',
  },
] as const

export const COURSEWARE_FILE_ACCEPT = COURSEWARE_FILE_FORMATS
  .flatMap(format => [format.extension, format.mime])
  .join(',')

export const COURSEWARE_FILE_ERROR = '仅接受 PDF、PPTX、DOCX 或 JPG 文件'

type CoursewareFileLike = Pick<File, 'name' | 'type'>

/** 文件选择和提交前共用的严格扩展名/MIME 白名单。 */
export function getCoursewareFileFormat(file: CoursewareFileLike | null) {
  if (!file || typeof file.name !== 'string' || typeof file.type !== 'string') {
    return null
  }

  const name = file.name.toLowerCase()
  return COURSEWARE_FILE_FORMATS.find(format => (
    name.endsWith(format.extension) && file.type === format.mime
  )) || null
}

export function isValidCoursewareFile(file: CoursewareFileLike | null) {
  return getCoursewareFileFormat(file) !== null
}
