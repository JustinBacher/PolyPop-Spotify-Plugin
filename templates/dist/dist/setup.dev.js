"use strict";

document.getElementById("spotify-sign-in-button").onclick = function () {
  var clientID = document.getElementById("client-id").value;
  var clientSecret = document.getElementById("client-secret").value;
  console.log("Hi");

  if (!clientID | !clientSecret) {
    document.getElementById("missing-modal").modal("show");
  }

  location.href = "/attempt-login?client-id=".concat(clientID.value, "&client-secret=").concat(clientSecret.value);
};