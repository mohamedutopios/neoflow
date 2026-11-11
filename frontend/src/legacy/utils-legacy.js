/* eslint-disable */
/*
 * Utilitaires d'affichage NeoFlow - reprise de l'ancien intranet (2015).
 * Ne pas modifier : utilise partout. Voir avec Marc avant toute evolution.
 */
var NeoUtils = (function () {

  function pad(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  function formatMontant(m) {
    if (m == null || m === '') return '-';
    var s = (Math.round(m * 100) / 100).toFixed(2);
    var parts = s.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return parts.join(',') + ' €';
  }

  function formatDate(d) {
    if (!d) return '';
    var dt = new Date(d);
    return pad(dt.getDate()) + '/' + pad(dt.getMonth() + 1) + '/' + dt.getFullYear();
  }

  // nombre de jours ouvres entre deux dates incluses (hors week-end)
  function joursOuvres(debut, fin) {
    var d = new Date(debut);
    var f = new Date(fin);
    var n = 0;
    while (d <= f) {
      var j = d.getDay();
      if (j != 0 && j != 6) n++;
      d.setDate(d.getDate() + 1);
    }
    return n;
  }

  return {
    formatMontant: formatMontant,
    formatDate: formatDate,
    joursOuvres: joursOuvres
  };
})();

export default NeoUtils;
