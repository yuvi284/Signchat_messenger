import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      // Proxy specific API endpoints that don't start with /api (if any are called directly without /api prefix)
      '/logout': 'http://localhost:5001',
      '/search_contact': 'http://localhost:5001',
      '/send-message': 'http://localhost:5001',
      '/save_contact': 'http://localhost:5001',
      '/get_saved_contacts': 'http://localhost:5001',
      '/get_messages': 'http://localhost:5001',
      '/get_contact_image': 'http://localhost:5001',
      '/mark_seen': 'http://localhost:5001',
      '/delete_message': 'http://localhost:5001',
      '/edit_contact_name': 'http://localhost:5001',
      '/delete_contact': 'http://localhost:5001',
      '/block_contact': 'http://localhost:5001',
      '/unblock_contact': 'http://localhost:5001',
      '/delete_contact_messages': 'http://localhost:5001',
      '/process_uploaded_video': 'http://localhost:5001',
      '/upload_video': 'http://localhost:5001',
      '/start_camera': 'http://localhost:5001',
      '/stop_camera': 'http://localhost:5001',
      '/get_final_sentence': 'http://localhost:5001',
      '/update_final_sentence': 'http://localhost:5001',
      '/isl_videos': 'http://localhost:5001',
      '/convert_to_isl': 'http://localhost:5001',
      '/feedback_message': 'http://localhost:5001',
      '/static': 'http://localhost:5001',
      '/socket.io': {
        target: 'http://localhost:5001',
        ws: true
      }
    },
  },
})
