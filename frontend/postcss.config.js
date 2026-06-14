export default {
  plugins: {
    autoprefixer: {
      overrideBrowserslist: [
        '> 1%',
        'last 3 versions',
        'not dead',
        'iOS >= 14',
        'Android >= 5',
        'Safari >= 14',
        'Firefox >= 78',
        'Chrome >= 80',
        'Edge >= 80'
      ]
    }
  }
}
