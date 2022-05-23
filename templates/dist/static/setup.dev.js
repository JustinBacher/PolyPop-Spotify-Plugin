"use strict";

document.getElementById("spotify-sign-in-button").onclick = function () {
  var clientID = document.getElementById("client-id").value;
  var clientSecret = document.getElementById("client-secret").value;

  if (!clientID | !clientSecret) {
    $('#missing-modal').modal('show');
  }

  location.href = "/attempt-login?client-id=".concat(clientID.value, "&client-secret=").concat(clientSecret.value);
};