import assert from 'node:assert/strict'
import {
  COURSEWARE_FILE_ACCEPT,
  getCoursewareFileFormat,
  isValidCoursewareFile,
} from '../src/config/coursewareFile.ts'

const validFiles = [
  ['slides.pdf', 'application/pdf', 'PDF'],
  ['slides.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'PPTX'],
  ['notes.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'DOCX'],
  ['photo.jpg', 'image/jpeg', 'JPG'],
]

for (const [name, type, label] of validFiles) {
  const file = { name, type }
  assert.equal(isValidCoursewareFile(file), true)
  assert.equal(getCoursewareFileFormat(file)?.label, label)
}

for (const file of [
  { name: 'slides.pdf', type: '' },
  { name: 'slides.pdf', type: 'application/octet-stream' },
  { name: 'slides.pdf', type: 'image/jpeg' },
  { name: 'slides.pptx', type: 'application/pdf' },
  { name: 'notes.docx', type: 'application/octet-stream' },
  { name: 'photo.jpg', type: 'application/pdf' },
  { name: 'photo.jpeg', type: 'image/jpeg' },
  { name: 'photo.jpg.exe', type: 'image/jpeg' },
  null,
]) {
  assert.equal(isValidCoursewareFile(file), false)
}

assert.equal(
  COURSEWARE_FILE_ACCEPT,
  '.pdf,application/pdf,.pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.jpg,image/jpeg',
)

console.log('courseware file validation: 4 valid and 9 invalid combinations passed')
